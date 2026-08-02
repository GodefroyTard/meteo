"""Lectures servies par l'API. Aucun calcul : les Verdicts sont déjà matérialisés."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Date, cast, distinct, extract, func, select

from meteo.domaine import qualite
from meteo.domaine.modeles import PAR_CLE
from meteo.domaine.rattachement import Rattachement, rattacher
from meteo.domaine.saison import Saison, heures_attendues, mois_de
from meteo.lots.verdicts import periode_observee
from meteo.stockage.session import session
from meteo.stockage.tables import Observation, Prevision, Station, Verdict

TEMPERATURE = "temperature"
PLUIE = "pluie"


def _colonnes(variable: str):
    """La paire de colonnes (Observation, Prévision) portant la variable demandée."""
    if variable == PLUIE:
        return Observation.precipitation_mm, Prevision.precipitation_mm
    return Observation.temperature_c, Prevision.temperature_c


@dataclass(frozen=True)
class LigneVerdict:
    modele: str
    nom_modele: str
    rang: int
    ecart_moyen: float
    biais: float | None
    fausses_alertes: float | None
    pluies_manquees: float | None
    ex_aequo: bool


@dataclass(frozen=True)
class CaseVerdict:
    station_code: str
    station_nom: str
    variable: str
    anticipation: int
    saison: str
    lignes: tuple[LigneVerdict, ...]
    nb_heures: int
    nb_jours: int
    couverture: float
    calcule_le: datetime

    @property
    def vainqueurs(self) -> tuple[str, ...]:
        return tuple(ligne.nom_modele for ligne in self.lignes if ligne.ex_aequo)


def stations_suivies() -> list[Station]:
    with session() as s:
        return list(
            s.execute(
                select(Station).where(Station.suivie.is_(True)).order_by(Station.nom)
            ).scalars()
        )


def rattachement(latitude: float, longitude: float, altitude: float) -> Rattachement:
    stations = [
        (s.code, s.nom, s.latitude, s.longitude, s.altitude) for s in stations_suivies()
    ]
    return rattacher(stations, latitude, longitude, altitude)


def case(
    station_code: str, variable: str, anticipation: int, saison: Saison
) -> CaseVerdict | None:
    """Le Verdict d'une case, ou None si elle n'a pas été publiée."""
    with session() as s:
        station = s.get(Station, station_code)
        if station is None:
            return None
        lignes = list(
            s.execute(
                select(Verdict)
                .where(
                    Verdict.station_code == station_code,
                    Verdict.variable == variable,
                    Verdict.anticipation == anticipation,
                    Verdict.saison == str(saison),
                )
                .order_by(Verdict.rang)
            ).scalars()
        )

    if not lignes:
        return None

    return CaseVerdict(
        station_code=station_code,
        station_nom=station.nom,
        variable=variable,
        anticipation=anticipation,
        saison=str(saison),
        lignes=tuple(
            LigneVerdict(
                modele=v.modele,
                nom_modele=PAR_CLE[v.modele].nom if v.modele in PAR_CLE else v.modele,
                rang=v.rang,
                ecart_moyen=v.ecart_moyen,
                biais=v.biais,
                fausses_alertes=v.fausses_alertes,
                pluies_manquees=v.pluies_manquees,
                ex_aequo=v.ex_aequo,
            )
            for v in lignes
        ),
        nb_heures=lignes[0].nb_heures,
        nb_jours=lignes[0].nb_jours,
        couverture=lignes[0].couverture,
        calcule_le=lignes[0].calcule_le,
    )


@dataclass(frozen=True)
class Manque:
    """Pourquoi une case de Verdict n'a pas été publiée.

    Un refus de conclure doit être motivé, sinon il se lit comme une panne.
    """

    heures_attendues: int
    heures_observees: int
    couverture: float
    seuil: float
    debut: date | None
    fin: date | None

    @property
    def jamais_collecte(self) -> bool:
        return self.heures_observees == 0


def manque(station_code: str, variable: str, saison: Saison) -> Manque:
    """Chiffre ce qui manque à une case pour être publiable.

    Deux comptages, pas de rééchantillonnage : assez léger pour rester dans l'API
    sans contredire le principe des Verdicts précalculés.
    """
    colonne, _ = _colonnes(variable)
    bornes = periode_observee()
    if bornes is None:
        return Manque(0, 0, 0.0, qualite.COUVERTURE_MINIMALE, None, None)

    debut, fin = bornes
    attendues = heures_attendues(debut, fin, saison)
    with session() as s:
        observees = (
            s.execute(
                select(func.count()).where(
                    Observation.station_code == station_code,
                    Observation.valide.is_(True),
                    colonne.is_not(None),
                    extract("month", Observation.instant).in_(mois_de(saison)),
                )
            ).scalar()
            or 0
        )

    return Manque(
        heures_attendues=attendues,
        heures_observees=observees,
        couverture=qualite.couverture(observees, attendues),
        seuil=qualite.COUVERTURE_MINIMALE,
        debut=debut,
        fin=fin,
    )


def saisons_publiees(station_code: str, variable: str) -> set[str]:
    """Les saisons pour lesquelles cette Station a un Verdict.

    Sert à signaler dans l'interface les saisons sans réponse, plutôt que de laisser
    l'utilisateur les sélectionner pour tomber sur un écran vide.
    """
    with session() as s:
        return set(
            s.execute(
                select(Verdict.saison).where(
                    Verdict.station_code == station_code,
                    Verdict.variable == variable,
                )
            )
            .scalars()
            .all()
        )


def anticipations_publiees(station_code: str, variable: str, saison: Saison) -> list[int]:
    with session() as s:
        return sorted(
            set(
                s.execute(
                    select(Verdict.anticipation).where(
                        Verdict.station_code == station_code,
                        Verdict.variable == variable,
                        Verdict.saison == str(saison),
                    )
                )
                .scalars()
                .all()
            )
        )


def _borne_temporelle(s, station_code: str, saison: Saison | None, heures: int) -> datetime:
    """Instant à partir duquel charger, pour obtenir les dernières `heures` observées.

    Sans saison c'est une simple fenêtre glissante. Avec, il faut remonter jusqu'à la
    dernière occurrence de cette saison — en août, l'hiver le plus récent a six mois.
    """
    if saison is None:
        return datetime.now(UTC) - timedelta(hours=heures)

    recentes = (
        s.execute(
            select(Observation.instant)
            .where(
                Observation.station_code == station_code,
                Observation.valide.is_(True),
                extract("month", Observation.instant).in_(mois_de(saison)),
            )
            .order_by(Observation.instant.desc())
            .limit(heures)
        )
        .scalars()
        .all()
    )
    if not recentes:
        return datetime.now(UTC) - timedelta(hours=heures)
    return recentes[-1]


@dataclass(frozen=True)
class Verification:
    """De quoi tracer les derniers jours : ce qui était annoncé, ce qui est tombé."""

    instants: tuple[datetime, ...]
    observations: tuple[float | None, ...]
    previsions: dict[str, tuple[float | None, ...]]
    variable: str = TEMPERATURE
    """La grandeur portée par les séries — elle décide de la forme du graphe."""


def verification(
    station_code: str,
    anticipation: int = 1,
    jours: int = 14,
    saison: Saison | None = None,
    variable: str = TEMPERATURE,
) -> Verification:
    """Séries alignées des Prévisions et des Observations sur les derniers jours.

    Restreintes à une saison lorsqu'elle est précisée : le graphe doit justifier le
    Verdict affiché, pas illustrer une autre période de l'année. On prend alors les
    jours les plus récents *de cette saison* présents en base, qui peuvent remonter
    à l'an dernier.
    """
    heures = jours * 24
    colonne_obs, colonne_prev = _colonnes(variable)

    with session() as s:
        borne = _borne_temporelle(s, station_code, saison, heures)

        conditions_obs = [
            Observation.station_code == station_code,
            Observation.valide.is_(True),
            Observation.instant >= borne,
        ]
        conditions_prev = [
            Prevision.station_code == station_code,
            Prevision.anticipation == anticipation,
            Prevision.instant >= borne,
        ]
        if saison is not None:
            mois = mois_de(saison)
            conditions_obs.append(extract("month", Observation.instant).in_(mois))
            conditions_prev.append(extract("month", Prevision.instant).in_(mois))

        obs = dict(
            s.execute(select(Observation.instant, colonne_obs).where(*conditions_obs)).all()
        )
        lignes = s.execute(
            select(Prevision.modele, Prevision.instant, colonne_prev).where(*conditions_prev)
        ).all()

    par_modele: dict[str, dict[datetime, float | None]] = {}
    for modele, instant, valeur in lignes:
        par_modele.setdefault(modele, {})[instant] = valeur

    instants = sorted(set(obs) | {i for serie in par_modele.values() for i in serie})

    # Ordre du catalogue, du plus fin au plus grossier : une couleur reste attachée
    # à un Modèle quelles que soient les séries présentes ou masquées.
    ordonnees = [cle for cle in PAR_CLE if cle in par_modele]
    ordonnees += [cle for cle in par_modele if cle not in PAR_CLE]

    return Verification(
        instants=tuple(instants),
        observations=tuple(obs.get(i) for i in instants),
        previsions={
            PAR_CLE[m].nom if m in PAR_CLE else m: tuple(par_modele[m].get(i) for i in instants)
            for m in ordonnees
        },
        variable=variable,
    )


FENETRE_NORMALE_J = 7
"""Demi-largeur de la fenêtre autour de la date, en jours. Quinze jours centrés sur
aujourd'hui : assez pour lisser un coup de chaud isolé, assez peu pour rester dans la
même saison."""


@dataclass(frozen=True)
class Normale:
    """Ce que cette Station mesure d'habitude à cette date.

    Ce n'est pas une normale climatique au sens de l'OMM, qui en demande trente ans :
    c'est la moyenne de ce que cette Station a réellement mesuré aux mêmes dates, les
    années précédentes. Le nombre d'années fait partie du résultat et s'affiche avec
    lui — sans lui, le chiffre prétendrait en savoir plus qu'il n'en sait.

    Aucune réanalyse n'entre ici (ADR 0003). Une moyenne de grille à 25 km ne dirait
    rien d'un fond de vallée à 220 m ni d'une crête à 1965 m ; celle-ci est mesurée au
    bon endroit, à la bonne altitude, et elle s'allongera d'une année chaque année.
    """

    max_c: float
    min_c: float
    annees: int
    jours: int
    """Nombre de journées mesurées entrant dans la moyenne."""


def normale(station_code: str, jour: date) -> Normale | None:
    """La moyenne des maximales et des minimales autour de cette date, années passées.

    L'année en cours est écartée : une moyenne qui contiendrait la semaine dernière
    se rapprocherait du temps qu'il fait, ce qui est exactement ce à quoi on veut la
    comparer.
    """
    with session() as s:
        # cast plutôt que date_trunc : ce dernier prend son unité en paramètre lié,
        # et Postgres ne reconnaît alors pas l'expression du GROUP BY comme la même.
        journee = cast(Observation.instant, Date)
        quotidien = (
            select(
                journee.label("jour"),
                func.max(Observation.temperature_c).label("maxi"),
                func.min(Observation.temperature_c).label("mini"),
            )
            .where(
                Observation.station_code == station_code,
                Observation.valide.is_(True),
                Observation.temperature_c.is_not(None),
            )
            .group_by(journee)
            .subquery()
        )

        rang = func.extract("doy", quotidien.c.jour)
        cible = jour.timetuple().tm_yday
        # Distance circulaire : à sept jours du 1er janvier, on veut fin décembre.
        ecart = func.least(func.abs(rang - cible), 365 - func.abs(rang - cible))

        ligne = s.execute(
            select(
                func.avg(quotidien.c.maxi),
                func.avg(quotidien.c.mini),
                func.count(distinct(func.extract("year", quotidien.c.jour))),
                func.count(),
            ).where(
                ecart <= FENETRE_NORMALE_J,
                func.extract("year", quotidien.c.jour) != jour.year,
            )
        ).one()

    maxi, mini, annees, jours = ligne
    if maxi is None or mini is None or not annees:
        return None
    return Normale(float(maxi), float(mini), int(annees), int(jours))


def dernier_rafraichissement() -> datetime | None:
    """Quand les Verdicts ont été recalculés pour la dernière fois.

    C'est la date de fin du dernier lot : le recalcul clôt toujours la mise à jour,
    donc l'horodatage le plus récent de la table dit quand les données ont cessé de
    vieillir. Rien à maintenir en mémoire — l'information est déjà en base.
    """
    with session() as s:
        return s.execute(select(func.max(Verdict.calcule_le))).scalar_one_or_none()
