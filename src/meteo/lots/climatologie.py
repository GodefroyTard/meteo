"""Chargement des Séries longues Météo-France.

Le fichier départemental porte l'identité de son Poste sur chaque ligne : on écrit les
deux tables dans la même traversée, sans second téléchargement. Les Postes doivent
précéder leurs Journées — c'est la clé étrangère qui l'impose, et c'est aussi l'ordre
qui a du sens : un jour ne se rattache pas à un lieu inconnu.

La couverture (`annees_pleines`) n'est pas déduite à la volée mais recalculée à la fin,
en base. C'est la seule mesure honnête : elle ne dépend ni de l'ordre des fichiers ni
du fait qu'on ait rechargé un département entier ou seulement sa dernière tranche.

Opération idempotente : recharger deux fois le même département ne crée pas de doublon
et ne perd rien.
"""

from collections.abc import Iterable, Iterator
from itertools import islice

from sqlalchemy import Integer, cast, extract, func, select, update
from sqlalchemy.dialects.postgresql import insert

from meteo.collecte.climatologie import ClientClimatologie, JourneeMesuree
from meteo.config import config
from meteo.domaine.tendance import ANNEES_MINIMUM, JOURS_ANNEE_PLEINE
from meteo.stockage.session import session
from meteo.stockage.tables import Journee, Poste

TAILLE_LOT = 5000


def _par_paquets(source: Iterable, taille: int) -> Iterator[list]:
    it = iter(source)
    while paquet := list(islice(it, taille)):
        yield paquet


def _ligne_poste(j: JourneeMesuree) -> dict:
    return {
        "numero": j.poste_numero,
        "nom": j.nom,
        "latitude": j.latitude,
        "longitude": j.longitude,
        "altitude": j.altitude,
        # Remplacés par _recalculer_couverture une fois toutes les Journées écrites.
        "premiere_annee": 0,
        "derniere_annee": 0,
        "annees_pleines": 0,
    }


MESURES = ("tn_c", "tx_c", "rr_mm", "etp_monteith_mm", "etp_grille_mm")


def _ligne_journee(j: JourneeMesuree) -> dict:
    """Toutes les colonnes de mesure, y compris celles que la passe ne remplit pas.

    Elles valent alors None, ce qui n'est utilisé qu'à l'insertion d'une Journée
    nouvelle : sur une Journée existante, seules les colonnes de la passe sont
    réécrites, et le reste survit intact.
    """
    return {
        "poste_numero": j.poste_numero,
        "jour": j.jour,
        **{champ: getattr(j, champ) for champ in MESURES},
    }


def _charger_flux(
    journees: Iterable[JourneeMesuree], colonnes: tuple[str, ...]
) -> tuple[int, set[str]]:
    """Écrit un flux de Journées, en ne réécrivant que les colonnes de sa famille."""
    connus: set[str] = set()
    total = 0
    with session() as s:
        for paquet in _par_paquets(journees, TAILLE_LOT):
            nouveaux = {j.poste_numero: j for j in paquet if j.poste_numero not in connus}
            if nouveaux:
                requete = insert(Poste)
                s.execute(
                    requete.on_conflict_do_update(
                        index_elements=["numero"],
                        # L'identité seule est rafraîchie : les statistiques de
                        # couverture appartiennent à _recalculer_couverture.
                        set_={
                            c: getattr(requete.excluded, c)
                            for c in ("nom", "latitude", "longitude", "altitude")
                        },
                    ),
                    [_ligne_poste(j) for j in nouveaux.values()],
                )
                connus.update(nouveaux)

            requete = insert(Journee)
            s.execute(
                requete.on_conflict_do_update(
                    index_elements=["poste_numero", "jour"],
                    set_={c: getattr(requete.excluded, c) for c in colonnes},
                ),
                [_ligne_journee(j) for j in paquet],
            )
            s.commit()
            total += len(paquet)
    return total, connus


def _charger_departement(client: ClientClimatologie, departement: str) -> tuple[int, int]:
    """Deux passes : le socle température-pluie, puis l'évapotranspiration.

    L'ordre compte peu — les deux passes se rejoignent sur la clé (Poste, jour) et
    n'écrivent que leurs propres colonnes — mais celui-ci met le socle en place le
    premier, ce qui rend les journaux plus lisibles quand la seconde passe échoue.
    """
    total, connus = _charger_flux(client.journees(departement), ("tn_c", "tx_c", "rr_mm"))
    autres, aussi = _charger_flux(
        client.evapotranspirations(departement), ("etp_monteith_mm", "etp_grille_mm")
    )
    return total + autres, len(connus | aussi)


def _recalculer_couverture() -> int:
    """Réécrit les statistiques de couverture de chaque Poste depuis les Journées.

    Quatre couvertures et non une : température, pluie et les deux évapotranspirations
    ne vont pas ensemble. Un Poste peut avoir un siècle de pluie et vingt ans de
    température, ou l'inverse ; les confondre ferait promettre à la page des graphes
    qu'elle ne saurait pas dessiner.

    Le comptage se fait en base et l'arbitrage en Python : agréger des comptages
    d'années par Poste tient en treize mille lignes, et le choix de la source
    d'évapotranspiration se lit mieux en une expression qu'en trois sous-requêtes.
    """
    annee = cast(extract("year", Journee.jour), Integer).label("annee")
    compte = lambda condition: func.count().filter(condition)  # noqa: E731
    par_annee = (
        select(
            Journee.poste_numero,
            annee,
            compte(Journee.tn_c.is_not(None) | Journee.tx_c.is_not(None)).label("temp"),
            compte(Journee.rr_mm.is_not(None)).label("pluie"),
            compte(Journee.etp_monteith_mm.is_not(None)).label("monteith"),
            compte(Journee.etp_grille_mm.is_not(None)).label("grille"),
        )
        .group_by(Journee.poste_numero, annee)
        .subquery()
    )

    with session() as s:
        lignes = s.execute(select(par_annee)).all()
        par_poste: dict[str, dict] = {}
        for ligne in lignes:
            etat = par_poste.setdefault(
                ligne.poste_numero,
                {"premiere": ligne.annee, "derniere": ligne.annee,
                 "temp": 0, "pluie": 0, "monteith": 0, "grille": 0},
            )
            etat["premiere"] = min(etat["premiere"], ligne.annee)
            etat["derniere"] = max(etat["derniere"], ligne.annee)
            for cle in ("temp", "pluie", "monteith", "grille"):
                if getattr(ligne, cle) >= JOURS_ANNEE_PLEINE:
                    etat[cle] += 1

        for numero, etat in par_poste.items():
            # Monteith d'abord partout où elle suffit : elle vient des mesures du
            # Poste, la grille d'une analyse (ADR 0009).
            if etat["monteith"] >= ANNEES_MINIMUM:
                source, annees_etp = "monteith", etat["monteith"]
            elif etat["grille"] >= ANNEES_MINIMUM:
                source, annees_etp = "grille", etat["grille"]
            else:
                source, annees_etp = None, 0
            s.execute(
                update(Poste)
                .where(Poste.numero == numero)
                .values(
                    premiere_annee=etat["premiere"],
                    derniere_annee=etat["derniere"],
                    annees_pleines=etat["temp"],
                    annees_pluie=etat["pluie"],
                    annees_etp=annees_etp,
                    source_etp=source,
                )
            )
        s.commit()
    return len(par_poste)


def charger(departements: list[str] | None = None) -> dict:
    """Charge les Séries longues des départements demandés.

    Sans argument, prend ceux de la configuration. Retourne de quoi écrire une ligne
    de journal : c'est un lot, il tourne sans témoin.
    """
    departements = departements or config().departements
    client = ClientClimatologie()
    try:
        journees = 0
        for departement in departements:
            n, _ = _charger_departement(client, departement)
            journees += n
    finally:
        client.close()

    return {
        "departements": departements,
        "journees": journees,
        "postes": _recalculer_couverture(),
    }
