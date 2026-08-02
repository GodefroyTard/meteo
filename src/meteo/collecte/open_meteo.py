"""Récupération des Prévisions passées auprès d'Open-Meteo.

L'API Previous Runs sert, pour un instant donné, ce que chaque Modèle en disait
N jours plus tôt — c'est elle qui rend le scoring rétroactif possible sans attendre
des mois de collecte.

Deux points structurants :

- `elevation` est forcée à l'altitude de la Station (ADR 0002), sans quoi la
  comparaison porterait sur le placement du relief lissé de chaque Modèle ;
- on n'interroge d'un Modèle que les Anticipations qu'il couvre réellement, pour
  ne pas gaspiller du quota sur des colonnes vides.

L'archive démarre le 20/01/2024 (AROME, ICON-D2) et le 04/02/2024 (ECMWF).
"""

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import httpx

from meteo.domaine.modeles import Modele

URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
URL_PREVISION = "https://api.open-meteo.com/v1/forecast"

JOURS_PAR_APPEL = 90
DELAI_ENTRE_APPELS_S = 1.0


@dataclass(frozen=True)
class ValeurPrevue:
    modele: str
    anticipation: int
    instant: datetime
    temperature_c: float | None
    precipitation_mm: float | None


def _tranches(debut: date, fin: date, jours: int) -> Iterator[tuple[date, date]]:
    curseur = debut
    while curseur <= fin:
        borne = min(curseur + timedelta(days=jours - 1), fin)
        yield curseur, borne
        curseur = borne + timedelta(days=1)


def _variables(modele: Modele) -> list[str]:
    return [
        f"{champ}_previous_day{a}"
        for a in range(1, modele.portee + 1)
        for champ in ("temperature_2m", "precipitation")
    ]


class ClientOpenMeteo:
    """Client minimal, synchrone et volontairement lent.

    Le service est gratuit ; on ne le bouscule pas.
    """

    def __init__(self, client: httpx.Client | None = None, delai_s: float = DELAI_ENTRE_APPELS_S):
        self._client = client or httpx.Client(timeout=120.0)
        self._delai_s = delai_s
        self._dernier_appel = 0.0

    def close(self) -> None:
        self._client.close()

    def _patienter(self) -> None:
        attente = self._delai_s - (time.monotonic() - self._dernier_appel)
        if attente > 0:
            time.sleep(attente)
        self._dernier_appel = time.monotonic()

    def previsions(
        self,
        latitude: float,
        longitude: float,
        altitude: float,
        modele: Modele,
        debut: date,
        fin: date,
    ) -> Iterator[ValeurPrevue]:
        """Toutes les Prévisions d'un Modèle pour une Station, sur une période."""
        for tranche_debut, tranche_fin in _tranches(debut, fin, JOURS_PAR_APPEL):
            self._patienter()
            reponse = self._client.get(
                URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "elevation": altitude,
                    "hourly": ",".join(_variables(modele)),
                    "models": modele.cle,
                    "start_date": tranche_debut.isoformat(),
                    "end_date": tranche_fin.isoformat(),
                    "timezone": "UTC",
                },
            )
            reponse.raise_for_status()
            corps = reponse.json()
            if "error" in corps:
                raise RuntimeError(f"Open-Meteo a refusé la requête : {corps.get('reason')}")
            yield from _lire(corps, modele)


def _lire(corps: dict, modele: Modele) -> Iterator[ValeurPrevue]:
    horaire = corps["hourly"]
    instants = [datetime.fromisoformat(t).replace(tzinfo=UTC) for t in horaire["time"]]

    for anticipation in range(1, modele.portee + 1):
        # Open-Meteo suffixe les colonnes du nom du modèle dès qu'on en demande un
        # explicitement ; on accepte les deux formes par sécurité.
        temperatures = _colonne(horaire, f"temperature_2m_previous_day{anticipation}", modele.cle)
        pluies = _colonne(horaire, f"precipitation_previous_day{anticipation}", modele.cle)
        if temperatures is None and pluies is None:
            continue

        for i, instant in enumerate(instants):
            t = temperatures[i] if temperatures else None
            p = pluies[i] if pluies else None
            if t is None and p is None:
                continue
            yield ValeurPrevue(modele.cle, anticipation, instant, t, p)


def _colonne(horaire: dict, base: str, cle_modele: str) -> list[float | None] | None:
    return horaire.get(f"{base}_{cle_modele}") or horaire.get(base)


@dataclass(frozen=True)
class HeurePrevue:
    instant: datetime
    temperature_c: float | None
    pluie_mm: float | None
    code_temps: int | None = None
    """Code WMO du Temps annoncé, ou None quand le Modèle n'en annonce pas."""

    jour: bool = True
    """Vrai entre lever et coucher du soleil — décide de l'icône : soleil ou lune."""


@dataclass(frozen=True)
class JourPrevu:
    jour: date
    min_c: float | None
    max_c: float | None
    pluie_mm: float | None
    code_temps: int | None = None


@dataclass(frozen=True)
class PrevisionCourante:
    """Ce qu'un Modèle annonce en ce moment pour un lieu."""

    modele: str
    maintenant_c: float | None
    maintenant_code: int | None = None
    """Le Temps annoncé pour l'heure en cours. AROME n'en fournit jamais."""

    maintenant_jour: bool = True
    vent_kmh: float | None = None
    rafales_kmh: float | None = None
    vent_degres: float | None = None
    uv: float | None = None
    """Indice UV à l'heure en cours. Seul GFS l'annonce parmi les Modèles suivis."""

    uv_max: float | None = None
    """Le maximum de la journée, atteint autour du midi solaire."""

    ressenti_c: float | None = None
    humidite_pct: float | None = None
    pression_hpa: float | None = None
    """Ramenée au niveau de la mer : c'est le nombre autour de 1013 que tout le monde
    reconnaît. La pression réelle à 905 m tourne autour de 916 et se ferait relire."""

    pression_avant_hpa: float | None = None
    """La pression trois heures plus tôt : c'est la tendance qui informe, pas la valeur.
    Absente avant 3 h du matin, faute d'heure de référence dans la série du jour."""

    isotherme_m: float | None = None
    """Altitude du 0 °C. Seuls ICON-D2, ICON-EU et GFS l'annoncent."""

    lever: datetime | None = None
    coucher: datetime | None = None
    lever_demain: datetime | None = None
    coucher_demain: datetime | None = None

    jours: tuple[JourPrevu, ...] = ()
    """Un élément par journée annoncée. La liste s'arrête où s'arrête le Modèle :
    AROME ne va pas au-delà de deux jours, ECMWF couvre la semaine entière."""

    heures: tuple[HeurePrevue, ...] = ()
    """Le détail horaire, à partir de l'heure en cours."""


FUSEAU = "Europe/Paris"
RECUL_PRESSION_H = 3
"""Le baromètre se lit sur trois heures : c'est la convention météorologique."""

JOURS_ANNONCES = 7
"""Profondeur de la prévision en vigueur. Une semaine : au-delà, seuls ECMWF et GFS
répondraient encore, et une carte à sept jours n'intéresse plus personne."""

FRAICHEUR_S = 900
"""Durée de validité du cache. Les runs sortent au mieux toutes les heures ; interroger
Open-Meteo à chaque affichage de page n'apporterait rien et le solliciterait pour rien."""


def _cle_cache(latitude: float, longitude: float, altitude: float) -> tuple:
    # Arrondi à ~100 m : deux visiteurs du même quartier partagent la même réponse.
    return (round(latitude, 3), round(longitude, 3), round(altitude))


_cache: dict[tuple, tuple[float, list[PrevisionCourante]]] = {}


def previsions_courantes(
    latitude: float, longitude: float, altitude: float, modeles: tuple[Modele, ...]
) -> list[PrevisionCourante]:
    """Ce que chaque Modèle annonce actuellement pour ce point.

    Rien à voir avec l'API Previous Runs : ici on interroge la prévision en vigueur,
    celle que l'utilisateur consulterait dans n'importe quelle application météo.
    L'altitude est forcée comme ailleurs (ADR 0002).

    Attention : le bloc `current` d'Open-Meteo ne se décline pas par modèle — il rend
    une valeur unique dont on ignore l'origine. La température « maintenant » est donc
    prise dans la série horaire, à l'heure en cours.
    """
    cle = _cle_cache(latitude, longitude, altitude)
    entree = _cache.get(cle)
    if entree and time.monotonic() - entree[0] < FRAICHEUR_S:
        return entree[1]

    champs_horaires = [
        "temperature_2m",
        "precipitation",
        "weather_code",
        "is_day",
        "wind_speed_10m",
        "wind_direction_10m",
        "wind_gusts_10m",
        "uv_index",
        "apparent_temperature",
        "relative_humidity_2m",
        "pressure_msl",
        "freezing_level_height",
    ]
    champs_jour = [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "weather_code",
        "uv_index_max",
        "sunrise",
        "sunset",
    ]
    reponse = httpx.get(
        URL_PREVISION,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "elevation": altitude,
            "models": ",".join(m.cle for m in modeles),
            "hourly": ",".join(champs_horaires),
            "daily": ",".join(champs_jour),
            "forecast_days": JOURS_ANNONCES,
            "timezone": FUSEAU,
        },
        timeout=45.0,
    )
    reponse.raise_for_status()
    corps = reponse.json()
    if "error" in corps:
        raise RuntimeError(f"Open-Meteo a refusé la requête : {corps.get('reason')}")

    resultat = _lire_courantes(corps, modeles)
    _cache[cle] = (time.monotonic(), resultat)
    return resultat


def _lire_courantes(corps: dict, modeles: tuple[Modele, ...]) -> list[PrevisionCourante]:
    horaire = corps["hourly"]
    quotidien = corps["daily"]
    i_maintenant = _index_heure_courante(horaire["time"])

    sorties = []
    for m in modeles:
        temperatures = horaire.get(f"temperature_2m_{m.cle}")
        maintenant = (
            temperatures[i_maintenant]
            if temperatures and i_maintenant < len(temperatures)
            else None
        )
        jours = _jours(quotidien, m.cle)
        if maintenant is None and not jours:
            continue  # Modèle absent de la réponse : on ne fabrique pas de carte vide.

        sorties.append(
            PrevisionCourante(
                modele=m.cle,
                maintenant_c=maintenant,
                maintenant_code=_a_l_heure(horaire, "weather_code", m.cle, i_maintenant),
                maintenant_jour=_a_l_heure(horaire, "is_day", m.cle, i_maintenant) != 0,
                vent_kmh=_a_l_heure(horaire, "wind_speed_10m", m.cle, i_maintenant),
                rafales_kmh=_a_l_heure(horaire, "wind_gusts_10m", m.cle, i_maintenant),
                vent_degres=_a_l_heure(horaire, "wind_direction_10m", m.cle, i_maintenant),
                uv=_a_l_heure(horaire, "uv_index", m.cle, i_maintenant),
                uv_max=_premier(quotidien, "uv_index_max", m.cle),
                ressenti_c=_a_l_heure(horaire, "apparent_temperature", m.cle, i_maintenant),
                humidite_pct=_a_l_heure(horaire, "relative_humidity_2m", m.cle, i_maintenant),
                pression_hpa=_a_l_heure(horaire, "pressure_msl", m.cle, i_maintenant),
                pression_avant_hpa=(
                    _a_l_heure(horaire, "pressure_msl", m.cle, i_maintenant - RECUL_PRESSION_H)
                    if i_maintenant >= RECUL_PRESSION_H
                    else None
                ),
                isotherme_m=_a_l_heure(horaire, "freezing_level_height", m.cle, i_maintenant),
                lever=_instant(_premier(quotidien, "sunrise", m.cle)),
                coucher=_instant(_premier(quotidien, "sunset", m.cle)),
                lever_demain=_instant(_rang(quotidien, "sunrise", m.cle, 1)),
                coucher_demain=_instant(_rang(quotidien, "sunset", m.cle, 1)),
                jours=jours,
                heures=_heures(horaire, m.cle, i_maintenant),
            )
        )
    return sorties


def _jours(bloc: dict, cle_modele: str) -> tuple[JourPrevu, ...]:
    """Les journées annoncées par un Modèle, jusqu'où il va.

    Une journée sans minimum ni maximum est au-delà de ce que le Modèle annonce :
    elle est écartée plutôt que rendue vide. La liste s'arrête donc d'elle-même, et
    l'interface peut dire « AROME ne va pas plus loin » sans avoir à le savoir.
    """
    dates = bloc.get("time") or []
    mins = bloc.get(f"temperature_2m_min_{cle_modele}") or []
    maxs = bloc.get(f"temperature_2m_max_{cle_modele}") or []
    pluies = bloc.get(f"precipitation_sum_{cle_modele}") or []
    codes = bloc.get(f"weather_code_{cle_modele}") or []

    sorties = []
    for i, jour in enumerate(dates):
        minimum = mins[i] if i < len(mins) else None
        maximum = maxs[i] if i < len(maxs) else None
        if minimum is None and maximum is None:
            continue
        sorties.append(
            JourPrevu(
                jour=date.fromisoformat(jour),
                min_c=minimum,
                max_c=maximum,
                pluie_mm=pluies[i] if i < len(pluies) else None,
                code_temps=_entier(codes[i]) if i < len(codes) else None,
            )
        )
    return tuple(sorties)


def _heures(horaire: dict, cle_modele: str, depuis: int) -> tuple[HeurePrevue, ...]:
    """Le détail horaire à partir de l'heure en cours.

    Les heures déjà écoulées sont écartées : dans une application météo, personne ne
    consulte la température prévue pour ce matin.
    """
    temperatures = horaire.get(f"temperature_2m_{cle_modele}") or []
    pluies = horaire.get(f"precipitation_{cle_modele}") or []
    codes = horaire.get(f"weather_code_{cle_modele}") or []
    jours = horaire.get(f"is_day_{cle_modele}") or []
    instants = horaire["time"]

    detail = []
    for i in range(depuis, len(instants)):
        t = temperatures[i] if i < len(temperatures) else None
        p = pluies[i] if i < len(pluies) else None
        if t is None and p is None:
            continue
        detail.append(
            HeurePrevue(
                instant=datetime.fromisoformat(instants[i]),
                temperature_c=t,
                pluie_mm=p,
                code_temps=_entier(codes[i]) if i < len(codes) else None,
                jour=(jours[i] != 0) if i < len(jours) and jours[i] is not None else True,
            )
        )
    return tuple(detail)


def _a_l_heure(horaire: dict, champ: str, cle_modele: str, rang: int):
    serie = horaire.get(f"{champ}_{cle_modele}")
    return serie[rang] if serie and rang < len(serie) else None


def _premier(bloc: dict, champ: str, cle_modele: str):
    """La valeur du jour même, dans le bloc quotidien."""
    return _rang(bloc, champ, cle_modele, 0)


def _rang(bloc: dict, champ: str, cle_modele: str, rang: int):
    serie = bloc.get(f"{champ}_{cle_modele}")
    return serie[rang] if serie and rang < len(serie) else None


def _instant(valeur) -> datetime | None:
    """Les heures de lever et de coucher arrivent en texte, sans fuseau."""
    return datetime.fromisoformat(valeur) if valeur else None


def _entier(valeur) -> int | None:
    """Les codes WMO arrivent parfois en flottant ; ils indexent un barème d'entiers."""
    return int(valeur) if valeur is not None else None


def _index_heure_courante(instants: list[str]) -> int:
    """Position de l'heure en cours dans la série horaire, exprimée en heure locale."""
    maintenant = datetime.now(ZoneInfo(FUSEAU)).replace(minute=0, second=0, microsecond=0)
    cible = maintenant.strftime("%Y-%m-%dT%H:00")
    try:
        return instants.index(cible)
    except ValueError:
        return 0


@lru_cache(maxsize=4096)
def altitude_du_point(latitude: float, longitude: float) -> float:
    """Altitude d'un point selon le modèle numérique de terrain à 90 m d'Open-Meteo.

    Nécessaire au rattachement : on compare l'altitude du lieu demandé à celle des
    Stations. Le résultat est mis en cache, la topographie changeant peu.
    """
    reponse = httpx.get(
        URL_PREVISION,
        params={"latitude": latitude, "longitude": longitude, "forecast_days": 1},
        timeout=30.0,
    )
    reponse.raise_for_status()
    return float(reponse.json()["elevation"])


URL_AIR = "https://air-quality-api.open-meteo.com/v1/air-quality"

POLLUANTS_AIR = ("pm2_5", "pm10", "nitrogen_dioxide", "ozone", "sulphur_dioxide")
"""Les polluants entrant dans l'indice européen. On demande les sous-indices déjà
calculés plutôt que les concentrations : la conversion en indice est normée, la
refaire ici serait s'exposer à une divergence silencieuse avec la source."""


@dataclass(frozen=True)
class AirBrut:
    """L'indice européen de qualité de l'air et le détail par polluant."""

    indice: float | None
    sous_indices: dict[str, float | None]


_cache_air: dict[tuple, tuple[float, AirBrut | None]] = {}


def qualite_air(latitude: float, longitude: float) -> AirBrut | None:
    """L'indice européen à l'heure en cours, pour ce point.

    Service distinct de la prévision : ce n'est pas un Modèle de prévision numérique
    mais l'analyse CAMS, et elle ne se décline donc pas par Modèle. Une indisponibilité
    ne doit pas emporter le reste de la page — d'où le None plutôt qu'une exception.
    """
    cle = (round(latitude, 2), round(longitude, 2))
    entree = _cache_air.get(cle)
    if entree and time.monotonic() - entree[0] < FRAICHEUR_S:
        return entree[1]

    champs = ["european_aqi"] + [f"european_aqi_{p}" for p in POLLUANTS_AIR]
    try:
        reponse = httpx.get(
            URL_AIR,
            params={
                "latitude": latitude,
                "longitude": longitude,
                "hourly": ",".join(champs),
                "forecast_days": 1,
                "timezone": FUSEAU,
            },
            timeout=30.0,
        )
        reponse.raise_for_status()
        corps = reponse.json()
        if "error" in corps:
            raise RuntimeError(corps.get("reason"))
        resultat = _lire_air(corps)
    except (httpx.HTTPError, RuntimeError, KeyError, ValueError):
        resultat = None

    _cache_air[cle] = (time.monotonic(), resultat)
    return resultat


def _lire_air(corps: dict) -> AirBrut:
    horaire = corps["hourly"]
    i = _index_heure_courante(horaire["time"])
    return AirBrut(
        indice=_a_l_heure_simple(horaire, "european_aqi", i),
        sous_indices={
            p: _a_l_heure_simple(horaire, f"european_aqi_{p}", i) for p in POLLUANTS_AIR
        },
    )


def _a_l_heure_simple(horaire: dict, champ: str, rang: int) -> float | None:
    """Sans suffixe de modèle : l'analyse de qualité de l'air n'en a pas."""
    serie = horaire.get(champ)
    return serie[rang] if serie and rang < len(serie) else None
