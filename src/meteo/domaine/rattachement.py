"""Choix de la Station de référence, et refus de rattacher.

L'air se refroidit d'environ 0,6 °C par 100 m d'altitude et varie bien plus lentement
à l'horizontale : 100 m de dénivelé « coûtent » donc autant que 10 km de distance.
Rattacher sur la distance seule attribuerait une station de crête à un habitant de
fond de vallée sous prétexte qu'elle est un peu plus proche à vol d'oiseau.
"""

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

RAYON_TERRE_KM = 6371.0

KM_PAR_100M_DENIVELE = 10.0
"""Taux de change entre dénivelé et distance dans le coût de rattachement."""

COUT_MAXIMAL_KM = 25.0
"""Au-delà, aucune Station n'est jugée comparable et rien n'est rattaché."""

COUT_MAXIMAL_CLIMAT_KM = 60.0
"""Plafond desserré pour le rattachement à un Poste climatologique.

Ce n'est pas un relâchement de la rigueur mais un changement de grandeur mesurée. Une
Observation sert à juger une Prévision : il faut alors qu'elle vaille pour le lieu, au
degré près, et 800 m de dénivelé la disqualifient. Une Série longue sert à montrer une
évolution : le réchauffement est cohérent à l'échelle d'une région, là où la température
absolue ne l'est pas. Le fond de vallée et l'alpage ne sont pas au même niveau, ils
montent ensemble.

La contrepartie est d'affichage, et elle est obligatoire : le Poste retenu doit toujours
être nommé avec son altitude et son écart au lieu, faute de quoi le lecteur croirait
lire la mémoire de son jardin."""


@dataclass(frozen=True)
class Candidate:
    """Une Station envisagée pour un lieu donné, avec ce qui l'en sépare."""

    code: str
    nom: str
    latitude: float
    longitude: float
    altitude: float
    distance_km: float
    denivele_m: float
    cout_km: float


@dataclass(frozen=True)
class Rattachement:
    """Le résultat d'une recherche de Station de référence.

    `reference` vaut None quand aucune Station n'est assez comparable : on préfère
    ne rien affirmer plutôt que présenter le verdict d'un autre massif.
    """

    reference: Candidate | None
    candidates: tuple[Candidate, ...]

    @property
    def rattache(self) -> bool:
        return self.reference is not None


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance orthodromique entre deux points, en kilomètres."""
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * RAYON_TERRE_KM * asin(sqrt(a))


def cout_km(distance: float, denivele: float) -> float:
    """Coût combiné distance/dénivelé, exprimé en kilomètres équivalents."""
    return distance + abs(denivele) / 100.0 * KM_PAR_100M_DENIVELE


def rattacher(
    stations: list[tuple[str, str, float, float, float]],
    latitude: float,
    longitude: float,
    altitude: float,
    cout_maximal_km: float = COUT_MAXIMAL_KM,
    nb_candidates: int = 3,
) -> Rattachement:
    """Désigne la Station de référence d'un lieu, ou refuse de le faire.

    `stations` est une liste de (code, nom, latitude, longitude, altitude).
    Les `candidates` retournées sont les plus proches au sens du coût combiné,
    qu'un rattachement ait eu lieu ou non — elles servent à expliquer le refus.
    """
    evaluees = []
    for code, nom, lat, lon, alt in stations:
        d = distance_km(latitude, longitude, lat, lon)
        denivele = alt - altitude
        evaluees.append(
            Candidate(
                code=code,
                nom=nom,
                latitude=lat,
                longitude=lon,
                altitude=alt,
                distance_km=d,
                denivele_m=denivele,
                cout_km=cout_km(d, denivele),
            )
        )

    evaluees.sort(key=lambda c: c.cout_km)
    meilleures = tuple(evaluees[:nb_candidates])
    reference = meilleures[0] if meilleures and meilleures[0].cout_km <= cout_maximal_km else None
    return Rattachement(reference=reference, candidates=meilleures)
