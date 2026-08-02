"""Calcul par lot des Verdicts.

Pour chaque case — Station × variable × Anticipation × saison — on aligne les
Prévisions des Modèles en lice sur les Observations valides, on vérifie que la
Couverture est suffisante, puis on compare.

Une case dont la Couverture est trop faible n'est simplement pas écrite : l'absence
de ligne *est* le refus de conclure (ADR 0005).
"""

from collections import defaultdict
from datetime import UTC, date, datetime

import numpy as np
from sqlalchemy import delete, func, select

from meteo.domaine import qualite
from meteo.domaine.modeles import ANTICIPATION_MAX, modeles_couvrant
from meteo.domaine.saison import Saison, heures_attendues, saison_de
from meteo.domaine.verdict import Comparaison, comparer_pluie, comparer_temperature
from meteo.lots.referentiel import suivies
from meteo.stockage.session import session
from meteo.stockage.tables import Observation, Prevision, Verdict

TEMPERATURE = "temperature"
PLUIE = "pluie"


def _observations(station_code: str) -> dict[datetime, tuple[float | None, float | None]]:
    with session() as s:
        lignes = s.execute(
            select(
                Observation.instant, Observation.temperature_c, Observation.precipitation_mm
            ).where(
                Observation.station_code == station_code,
                Observation.valide.is_(True),
            )
        ).all()
    return {instant: (t, p) for instant, t, p in lignes}


def _previsions(
    station_code: str, anticipation: int
) -> dict[str, dict[datetime, tuple[float | None, float | None]]]:
    with session() as s:
        lignes = s.execute(
            select(
                Prevision.modele,
                Prevision.instant,
                Prevision.temperature_c,
                Prevision.precipitation_mm,
            ).where(
                Prevision.station_code == station_code,
                Prevision.anticipation == anticipation,
            )
        ).all()

    par_modele: dict[str, dict[datetime, tuple[float | None, float | None]]] = defaultdict(dict)
    for modele, instant, t, p in lignes:
        par_modele[modele][instant] = (t, p)
    return par_modele


def _aligner(
    observations: dict[datetime, tuple[float | None, float | None]],
    previsions: dict[str, dict[datetime, tuple[float | None, float | None]]],
    saison: Saison,
    indice: int,
    debut: date,
    fin: date,
) -> tuple[np.ndarray, np.ndarray, dict[str, np.ndarray]] | None:
    """Restreint aux instants où la saison correspond et où tout le monde a une valeur.

    `indice` désigne la variable dans les tuples stockés : 0 pour la température,
    1 pour la précipitation. Retourne (jours, observations, prévisions par Modèle),
    ou None si l'alignement ne laisse rien.

    Le filtrage sur [debut, fin] est le même que celui qui sert de dénominateur à la
    Couverture : sans cela, une Observation hors période gonflerait le numérateur.
    """
    instants = sorted(
        instant
        for instant, valeurs in observations.items()
        if valeurs[indice] is not None
        and debut <= instant.date() <= fin
        and saison_de(instant.date()) is saison
    )
    for serie in previsions.values():
        instants = [i for i in instants if serie.get(i, (None, None))[indice] is not None]

    if not instants:
        return None

    jours = np.array([i.date().toordinal() for i in instants])
    reel = np.array([observations[i][indice] for i in instants], dtype=float)
    annonces = {
        modele: np.array([serie[i][indice] for i in instants], dtype=float)
        for modele, serie in previsions.items()
    }
    return jours, reel, annonces


def _lignes(
    station_code: str,
    variable: str,
    anticipation: int,
    saison: Saison,
    comparaison: Comparaison,
    couverture: float,
    calcule_le: datetime,
) -> list[dict]:
    return [
        {
            "station_code": station_code,
            "variable": variable,
            "anticipation": anticipation,
            "saison": str(saison),
            "modele": score.modele,
            "rang": rang,
            "ecart_moyen": score.ecart_moyen,
            "biais": score.biais,
            "fausses_alertes": score.fausses_alertes,
            "pluies_manquees": score.pluies_manquees,
            "ex_aequo": score.ex_aequo,
            "nb_heures": comparaison.nb_heures,
            "nb_jours": comparaison.nb_jours,
            "couverture": couverture,
            "calcule_le": calcule_le,
        }
        for rang, score in enumerate(comparaison.scores, start=1)
    ]


def periode_observee() -> tuple[date, date] | None:
    """La plage réellement couverte par les Observations en base.

    C'est elle qui sert de période de référence par défaut, et non la date de début
    configurée : compter la Couverture sur une plage qu'on n'a jamais collectée
    ferait tomber toutes les cases sous le seuil, et n'en publierait aucune.
    """
    with session() as s:
        bornes = s.execute(
            select(func.min(Observation.instant), func.max(Observation.instant))
        ).one()
    if bornes[0] is None:
        return None
    return bornes[0].date(), bornes[1].date()


def calculer(debut: date | None = None, fin: date | None = None) -> int:
    """Recalcule l'intégralité des Verdicts et remplace la table.

    Le remplacement est global et transactionnel : à aucun moment l'API ne sert un
    mélange d'anciens et de nouveaux Verdicts.
    """
    if debut is None or fin is None:
        observee = periode_observee()
        if observee is None:
            return 0
        debut = debut or observee[0]
        fin = fin or observee[1]
    calcule_le = datetime.now(UTC)

    toutes: list[dict] = []
    for station in suivies():
        observations = _observations(station.code)
        if not observations:
            continue

        for anticipation in range(1, ANTICIPATION_MAX + 1):
            en_lice = {m.cle for m in modeles_couvrant(anticipation)}
            previsions = {
                cle: serie
                for cle, serie in _previsions(station.code, anticipation).items()
                if cle in en_lice
            }
            if len(previsions) < 2:
                continue

            for saison in Saison:
                attendues = heures_attendues(debut, fin, saison)
                if not attendues:
                    continue

                for variable, indice, comparer in (
                    (TEMPERATURE, 0, comparer_temperature),
                    (PLUIE, 1, comparer_pluie),
                ):
                    aligne = _aligner(observations, previsions, saison, indice, debut, fin)
                    if aligne is None:
                        continue
                    jours, reel, annonces = aligne

                    couverture = qualite.couverture(len(reel), attendues)
                    if not qualite.publiable(len(reel), attendues):
                        continue

                    comparaison = comparer(jours, annonces, reel)
                    toutes.extend(
                        _lignes(
                            station.code,
                            variable,
                            anticipation,
                            saison,
                            comparaison,
                            couverture,
                            calcule_le,
                        )
                    )

    with session() as s:
        s.execute(delete(Verdict))
        if toutes:
            s.execute(Verdict.__table__.insert(), toutes)
        s.commit()

    return len(toutes)
