"""Nommer un point : de quelle commune s'agit-il ?

Quand l'utilisateur se géolocalise, la page doit dire où il est — pas où se trouve la
Station qui lui sert de référence. Ce sont deux lieux différents, et les confondre
laisserait croire que la prévision affichée est celle de la Station.

On interroge le découpage administratif de l'État plutôt qu'un géocodeur d'adresses.
La Base Adresse Nationale est plus précise en ville mais ne répond rien en montagne —
vérifié au Grand Veymont, à Chamrousse et à Lans-en-Vercors, c'est-à-dire précisément
là où la question se pose. Le découpage communal, lui, couvre chaque mètre carré du
territoire : tout point de France est dans une commune.

Hors de France, l'API rend une liste vide. La page retombe alors sur « Votre
position », ce qui est vrai et suffisant.

Service public, sans jeton ni quota déclaré. En cas d'échec on rend None : nommer le
lieu est un confort, pas une condition pour afficher la météo.
"""

from dataclasses import dataclass
from functools import lru_cache

import httpx

URL_COMMUNES = "https://geo.api.gouv.fr/communes"

DECIMALES_CACHE = 3
"""Trois décimales, soit environ cent mètres. Deux points d'un même quartier partagent
ainsi leur entrée de cache, et une commune ne change pas sur cent mètres."""


@dataclass(frozen=True)
class Commune:
    nom: str
    departement: str | None


def lire_reponse(corps: list) -> Commune | None:
    """La première commune de la réponse, ou None si le point est hors de France."""
    if not corps:
        return None
    premiere = corps[0]
    nom = premiere.get("nom")
    if not nom:
        return None
    return Commune(nom=nom, departement=premiere.get("codeDepartement"))


@lru_cache(maxsize=512)
def commune(latitude: float, longitude: float, timeout: float = 6.0) -> Commune | None:
    """La commune d'un point, ou None.

    Le délai est court et l'échec silencieux : cet appel est sur le chemin de rendu de
    la page d'accueil, et un service administratif lent ne doit pas retarder la météo.
    """
    try:
        reponse = httpx.get(
            URL_COMMUNES,
            params={
                "lat": round(latitude, DECIMALES_CACHE),
                "lon": round(longitude, DECIMALES_CACHE),
                "fields": "nom,codeDepartement",
            },
            timeout=timeout,
        )
        reponse.raise_for_status()
        return lire_reponse(reponse.json())
    except (httpx.HTTPError, ValueError):
        return None
