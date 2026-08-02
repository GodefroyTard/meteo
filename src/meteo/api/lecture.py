"""Lectures servies par l'API. Aucun calcul : les Verdicts sont déjà matérialisés."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Date, cast, distinct, extract, func, select

from meteo.domaine import cycle, indicateurs, neige, qualite, secheresse, tendance
from meteo.domaine.modeles import PAR_CLE
from meteo.domaine.rattachement import COUT_MAXIMAL_CLIMAT_KM, Rattachement, rattacher
from meteo.domaine.saison import Saison, heures_attendues, mois_de
from meteo.lots.verdicts import periode_observee
from meteo.stockage.session import session
from meteo.stockage.tables import Journee, Observation, Poste, Prevision, Station, Verdict

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


@dataclass(frozen=True)
class PosteResume:
    """Un Poste climatologique et l'étendue de ce qu'il a mesuré."""

    numero: str
    nom: str
    latitude: float
    longitude: float
    altitude: float
    premiere_annee: int
    derniere_annee: int
    annees_pleines: int
    annees_pluie: int
    annees_etp: int
    annees_neige: int
    source_etp: str | None

    @property
    def nom_lisible(self) -> str:
        """Le nom du Poste en casse de titre.

        Météo-France publie « AUTRANS », « GRENOBLE-ST GEOIRS ». On conserve la valeur
        publiée en base — c'est elle qui fait foi — et on ne l'adoucit qu'à l'affichage,
        où des capitales criardes rendraient la phrase désagréable à lire.
        """
        return self.nom.title()


@dataclass(frozen=True)
class SerieJour:
    """Ce qu'un Poste a mesuré un jour de l'année, année après année.

    `tendance_max` et `tendance_min` valent None quand la Série ne porte pas assez
    d'années : la page montre alors le nuage sans droite, plutôt qu'une droite qui
    n'engage rien.
    """

    poste: PosteResume
    mois: int
    jour: int
    maxima: tuple[tendance.AnneeAgregee, ...]
    minima: tuple[tendance.AnneeAgregee, ...]
    tendance_max: tendance.Tendance | None
    tendance_min: tendance.Tendance | None


@dataclass(frozen=True)
class SerieCycle:
    """Toutes les années d'un Poste, superposées sur l'axe des quantièmes."""

    poste: PosteResume
    annees: tuple[cycle.CycleAnnuel, ...]
    decennies: tuple[int, ...]
    """Les années mises en avant : la plus récente, puis de dix en dix."""


@dataclass(frozen=True)
class SerieFranchissement:
    """Le décompte annuel d'un seuil, et sa pente s'il y a assez d'années."""

    seuil: indicateurs.Seuil
    annees: tuple[indicateurs.AnneeComptee, ...]
    tendance: tendance.Tendance | None


@dataclass(frozen=True)
class SerieGel:
    """Les saisons sans gel d'un Poste, et l'allongement de leur durée."""

    saisons: tuple[indicateurs.SaisonSansGel, ...]
    tendance: tendance.Tendance | None


@dataclass(frozen=True)
class SerieRecords:
    """La répartition des records dans le temps, chaud et froid séparés.

    Les deux se lisent ensemble : un climat stable les répartit également, un climat qui
    se réchauffe voit les records de chaleur s'accumuler à mesure que ceux de froid
    cessent d'être battus.
    """

    chaleur: tuple[indicateurs.PartDecennie, ...]
    froid: tuple[indicateurs.PartDecennie, ...]
    dernier_chaud: int | None
    """Année du record de chaleur le plus récent."""

    dernier_froid: int | None


@dataclass(frozen=True)
class SerieSecheresse:
    """Le bilan hydrique estival d'un Poste, saison après saison.

    `source` dit d'où vient la demande évaporative — « monteith » quand elle est
    calculée depuis les mesures du Poste, « grille » quand elle est interpolée. La
    page doit le nommer : l'écart entre les deux n'est pas anecdotique (ADR 0009).
    """

    source: str
    bilans: tuple[secheresse.BilanSaison, ...]
    etats: tuple[secheresse.EtatSec, ...]
    frequences: tuple[secheresse.FrequenceDecennie, ...]
    tendance_bilan: tendance.Tendance | None
    tendance_apport: tendance.Tendance | None
    tendance_demande: tendance.Tendance | None


@dataclass(frozen=True)
class SerieNeige:
    """L'enneigement d'un Poste, saison après saison.

    Deux tendances et non une : la durée et l'intensité de l'enneigement ne se
    résument pas l'une l'autre, et n'ont pas la même unité.
    """

    saisons: tuple[neige.SaisonNeige, ...]
    tendance_jours: tendance.Tendance | None
    tendance_epaisseur: tendance.Tendance | None


@dataclass(frozen=True)
class DossierClimat:
    """Tout ce que la page climat montre d'un Poste, chargé en une fois."""

    poste: PosteResume
    jour: SerieJour
    cycle: SerieCycle
    franchissements: tuple[SerieFranchissement, ...]
    gel: SerieGel
    records: SerieRecords
    neige: SerieNeige | None
    secheresse: SerieSecheresse | None

    dernier_jour: date | None
    """Dernier jour mesuré par ce Poste, toutes grandeurs confondues. Il borne tous
    les graphes de la page, et son écart à `derniere_journee_chargee` dit si le Poste
    mesure encore ou s'il s'est tu."""
    """None quand le Poste n'a pas d'évapotranspiration exploitable — deux Postes sur
    trois en Isère. On préfère l'absence de section à une section approximative."""


def _resume_poste(p: Poste) -> PosteResume:
    return PosteResume(
        numero=p.numero,
        nom=p.nom,
        latitude=p.latitude,
        longitude=p.longitude,
        altitude=p.altitude,
        premiere_annee=p.premiere_annee,
        derniere_annee=p.derniere_annee,
        annees_pleines=p.annees_pleines,
        annees_pluie=p.annees_pluie,
        annees_etp=p.annees_etp,
        annees_neige=p.annees_neige,
        source_etp=p.source_etp,
    )


def postes_utilisables(minimum: int = tendance.ANNEES_MINIMUM) -> list[PosteResume]:
    """Les Postes portant assez d'années pleines pour qu'une tendance ait un sens.

    Trier par couverture décroissante n'est pas cosmétique : c'est l'ordre dans lequel
    on veut qu'un lecteur découvre la liste, la meilleure série d'abord.
    """
    with session() as s:
        lignes = s.execute(
            select(Poste)
            .where(Poste.annees_pleines >= minimum)
            .order_by(Poste.annees_pleines.desc(), Poste.nom)
        ).scalars()
        return [_resume_poste(p) for p in lignes]


def rattachement_climatique(latitude: float, longitude: float, altitude: float) -> Rattachement:
    """Le Poste le plus comparable à un lieu, au sens du coût desserré pour le climat."""
    postes = postes_utilisables()
    return rattacher(
        [(p.numero, p.nom, p.latitude, p.longitude, p.altitude) for p in postes],
        latitude,
        longitude,
        altitude,
        cout_maximal_km=COUT_MAXIMAL_CLIMAT_KM,
    )


def _mois_voisins(mois: int) -> list[int]:
    """Le mois visé et ses deux voisins.

    La fenêtre ne déborde jamais au-delà : quinze jours centrés ne peuvent toucher que
    trois mois. Restreindre la requête à ces trois-là évite de rapatrier soixante-quinze
    ans de mesures pour n'en garder qu'un quinzième.
    """
    return sorted({(mois - 2) % 12 + 1, mois, mois % 12 + 1})


def _series_completes(s, poste_numero: str, source_etp: str | None):
    """Les quatre séries d'un Poste : minima, maxima, pluie, demande évaporative.

    La colonne d'évapotranspiration retenue dépend du Poste — Monteith là où elle
    existe, la grille ailleurs. Charger les deux et trancher ici plutôt qu'en base
    évite une requête conditionnelle pour une décision déjà prise à l'ingestion.
    """
    lignes = s.execute(
        select(
            Journee.jour,
            Journee.tn_c,
            Journee.tx_c,
            Journee.rr_mm,
            Journee.etp_monteith_mm,
            Journee.etp_grille_mm,
            Journee.neige_cm,
            Journee.neige_fraiche_cm,
        ).where(Journee.poste_numero == poste_numero)
    ).all()

    colonne = "etp_monteith_mm" if source_etp == "monteith" else "etp_grille_mm"
    return (
        {r.jour: r.tn_c for r in lignes if r.tn_c is not None},
        {r.jour: r.tx_c for r in lignes if r.tx_c is not None},
        {r.jour: r.rr_mm for r in lignes if r.rr_mm is not None},
        {r.jour: getattr(r, colonne) for r in lignes if getattr(r, colonne) is not None},
        {r.jour: r.neige_cm for r in lignes if r.neige_cm is not None},
        {r.jour: r.neige_fraiche_cm for r in lignes if r.neige_fraiche_cm is not None},
    )


def _extremes(s, poste_numero: str, mois: list[int] | None = None):
    """Les minima et maxima d'un Poste, indexés par jour.

    Une seule lecture sert tous les indicateurs de la page : les rapatrier séparément
    coûterait six fois le même parcours d'index pour six vues des mêmes journées.
    """
    conditions = [Journee.poste_numero == poste_numero]
    if mois is not None:
        conditions.append(extract("month", Journee.jour).in_(mois))
    lignes = s.execute(
        select(Journee.jour, Journee.tn_c, Journee.tx_c).where(*conditions)
    ).all()
    minima = {ligne.jour: ligne.tn_c for ligne in lignes if ligne.tn_c is not None}
    maxima = {ligne.jour: ligne.tx_c for ligne in lignes if ligne.tx_c is not None}
    return minima, maxima


def _serie_jour(resume: PosteResume, minima, maxima, mois: int, jour: int) -> SerieJour:
    annees = range(resume.premiere_annee, resume.derniere_annee + 1)
    agregees_max = tendance.agreger(maxima, mois, jour, annees)
    agregees_min = tendance.agreger(minima, mois, jour, annees)
    return SerieJour(
        poste=resume,
        mois=mois,
        jour=jour,
        maxima=tuple(agregees_max),
        minima=tuple(agregees_min),
        tendance_max=tendance.ajuster(agregees_max),
        tendance_min=tendance.ajuster(agregees_min),
    )


def _cycle(resume: PosteResume, minima, maxima) -> SerieCycle:
    annees = cycle.cycles(cycle.lisser(cycle.moyennes_quotidiennes(minima, maxima)))
    if not annees:
        return SerieCycle(poste=resume, annees=(), decennies=())
    presentes = {a.annee for a in annees}
    reperes = [
        annee
        for annee in cycle.decennies(annees[-1].annee, annees[0].annee)
        if annee in presentes
    ]
    return SerieCycle(poste=resume, annees=tuple(annees), decennies=tuple(reperes))


def _pente(valeurs: list[tuple[int, float]]) -> tendance.Tendance | None:
    """Ajuste une droite sur des couples (année, valeur), quelle que soit l'unité."""
    return tendance.ajuster(
        [tendance.AnneeAgregee(annee=a, valeur=v, nb_jours=1) for a, v in valeurs]
    )


def _franchissements(minima, maxima) -> tuple[SerieFranchissement, ...]:
    series = []
    for seuil in indicateurs.SEUILS:
        comptes = indicateurs.compter(
            minima if seuil.variable == "minima" else maxima, seuil
        )
        series.append(
            SerieFranchissement(
                seuil=seuil,
                annees=tuple(comptes),
                tendance=_pente([(c.annee, float(c.jours)) for c in comptes]),
            )
        )
    return tuple(series)


def _gel(minima) -> SerieGel:
    saisons = indicateurs.saisons_sans_gel(minima)
    return SerieGel(
        saisons=tuple(saisons),
        tendance=_pente([(s.annee, float(s.duree)) for s in saisons]),
    )


SILENCE_POSTE_J = 60
"""Au-delà de cet écart avec la journée la plus récente du département, un Poste est
tenu pour silencieux. Deux mois : assez pour absorber un retard de publication, assez
peu pour ne pas laisser croire qu'un Poste éteint depuis des années mesure encore."""


def derniere_journee_chargee() -> date | None:
    """Le jour le plus récent présent dans les Séries longues, tous Postes confondus.

    Sert de repère de fraîcheur : c'est lui qui avance quand le lot hebdomadaire
    tourne, et qui se fige quand il tombe en panne.
    """
    with session() as s:
        return s.execute(select(func.max(Journee.jour))).scalar_one_or_none()


def _neige(hauteurs, fraiches) -> SerieNeige | None:
    """L'enneigement, ou rien si le Poste ne relève pas la hauteur de neige."""
    if not hauteurs:
        return None
    saisons = neige.saisons(hauteurs, fraiches)
    if not saisons:
        return None
    return SerieNeige(
        saisons=tuple(saisons),
        tendance_jours=_pente([(s.saison, float(s.jours_au_sol)) for s in saisons]),
        tendance_epaisseur=_pente([(s.saison, s.epaisseur_max_cm) for s in saisons]),
    )


def _secheresse(resume: PosteResume, pluie, etp) -> SerieSecheresse | None:
    """Le bilan hydrique estival, ou rien.

    Rien plutôt qu'une approximation : sans évapotranspiration mesurée ou analysée, la
    seule voie serait de l'estimer depuis la température, ce qui sous-estime la tendance
    d'un facteur deux et demi (ADR 0009).
    """
    if not resume.source_etp or not pluie or not etp:
        return None
    saisons = secheresse.bilans(pluie, etp)
    etats = secheresse.standardiser(saisons)
    return SerieSecheresse(
        source=resume.source_etp,
        bilans=tuple(saisons),
        etats=tuple(etats),
        frequences=tuple(secheresse.frequences(etats)),
        tendance_bilan=_pente([(b.annee, b.bilan_mm) for b in saisons]),
        tendance_apport=_pente([(b.annee, b.apport_mm) for b in saisons]),
        tendance_demande=_pente([(b.annee, b.demande_mm) for b in saisons]),
    )


def _records(minima, maxima) -> SerieRecords:
    chauds = indicateurs.records(maxima, au_plus_haut=True)
    froids = indicateurs.records(minima, au_plus_haut=False)
    return SerieRecords(
        chaleur=tuple(indicateurs.parts_par_decennie(maxima, chauds)),
        froid=tuple(indicateurs.parts_par_decennie(minima, froids)),
        dernier_chaud=max((r.annee for r in chauds), default=None),
        dernier_froid=max((r.annee for r in froids), default=None),
    )


def serie_jour(poste_numero: str, mois: int, jour: int) -> SerieJour | None:
    """Les maxima et minima de ce jour de l'année, année après année, avec leur tendance.

    Lecture restreinte aux trois mois utiles : c'est le point d'entrée de l'API, qui n'a
    pas besoin du reste. La page, elle, passe par `dossier`.
    """
    with session() as s:
        poste = s.get(Poste, poste_numero)
        if poste is None:
            return None
        resume = _resume_poste(poste)
        minima, maxima = _extremes(s, poste_numero, _mois_voisins(mois))
    return _serie_jour(resume, minima, maxima, mois, jour)


def dossier(poste_numero: str, mois: int, jour: int) -> DossierClimat | None:
    """Tout ce que la page climat montre, depuis une seule lecture de la Série longue.

    Rend None si le Poste est inconnu. Un Poste connu mais pauvre rend un dossier aux
    tendances nulles : les nuages de points restent montrables, les droites non.
    """
    with session() as s:
        poste = s.get(Poste, poste_numero)
        if poste is None:
            return None
        resume = _resume_poste(poste)
        (minima, maxima, pluie, etp, hauteurs, fraiches) = _series_completes(
            s, poste_numero, poste.source_etp
        )

    jours_mesures = (
        minima.keys() | maxima.keys() | pluie.keys() | etp.keys() | hauteurs.keys()
    )
    return DossierClimat(
        dernier_jour=max(jours_mesures) if jours_mesures else None,
        poste=resume,
        jour=_serie_jour(resume, minima, maxima, mois, jour),
        cycle=_cycle(resume, minima, maxima),
        franchissements=_franchissements(minima, maxima),
        gel=_gel(minima),
        records=_records(minima, maxima),
        neige=_neige(hauteurs, fraiches),
        secheresse=_secheresse(resume, pluie, etp),
    )
