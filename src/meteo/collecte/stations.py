"""Import du référentiel des Stations du réseau StatIC.

Le fichier est publié en open data et ne demande aucune authentification.
Source : https://www.infoclimat.fr/opendata/
"""

from dataclasses import dataclass
from datetime import date

import httpx

from meteo.domaine.rattachement import distance_km

URL_STATIONS = "https://www.infoclimat.fr/opendata/stations_xhr.php?format=geojson"

DELAI_INACTIVITE_JOURS = 30
"""Une Station sans mesure depuis plus longtemps est tenue pour éteinte."""


@dataclass(frozen=True)
class StationTrouvee:
    code: str
    nom: str
    latitude: float
    longitude: float
    altitude: float
    derniere_activite: date | None
    distance_km: float


def _lire_date(brut: str | None) -> date | None:
    # Le champ vaut "0000-00-00T00:00:00Z" pour les Stations n'ayant jamais émis.
    if not brut or brut.startswith("0000"):
        return None
    try:
        return date.fromisoformat(brut[:10])
    except ValueError:
        return None


def telecharger(client: httpx.Client | None = None) -> list[dict]:
    proprietaire = client is None
    client = client or httpx.Client(timeout=60.0)
    try:
        reponse = client.get(URL_STATIONS)
        reponse.raise_for_status()
        return reponse.json()["features"]
    finally:
        if proprietaire:
            client.close()


def autour(
    features: list[dict],
    latitude: float,
    longitude: float,
    rayon_km: float,
    aujourdhui: date,
) -> list[StationTrouvee]:
    """Les Stations actives dans le rayon demandé, de la plus proche à la plus lointaine."""
    trouvees = []
    for f in features:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        d = distance_km(latitude, longitude, lat, lon)
        if d > rayon_km:
            continue

        derniere = _lire_date(p.get("last_activity"))
        if derniere is None or (aujourdhui - derniere).days > DELAI_INACTIVITE_JOURS:
            continue

        trouvees.append(
            StationTrouvee(
                code=p["id"],
                nom=p.get("name") or p["id"],
                latitude=lat,
                longitude=lon,
                altitude=float(p["elevation"]),
                derniere_activite=derniere,
                distance_km=d,
            )
        )

    trouvees.sort(key=lambda s: s.distance_km)
    return trouvees
