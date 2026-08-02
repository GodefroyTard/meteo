"""Récupération des Séries longues auprès de Météo-France (data.gouv.fr).

Le jeu « Données climatologiques de base - quotidiennes » publie, par département, les
minima et maxima quotidiens de chaque Poste depuis 1950 — et avant, quand le Poste
existait. L'Isère entière tient dans 18 Mo compressés, sans jeton ni quota : on
télécharge le département en entier plutôt que d'interroger poste par poste.

Licence ouverte LOV2 : la réutilisation est libre, la mention de la source obligatoire.

Les noms de fichiers embarquent leur période (« previous-1950-2024 »,
« latest-2025-2026 ») et changeront donc au fil des ans. On les résout par le
catalogue data.gouv plutôt que de les figer, sans quoi la collecte casserait
silencieusement à la première republication.

Codes qualité, tels que servis dans les colonnes Q* :

- 1 : valeur validée ;
- 9 : valeur filtrée automatiquement, non revalidée à la main ;
- 0 et 2 : valeur protégée ou douteuse.

On retient 1 et 9, on écarte 0 et 2. Écarter aussi les 9 paraîtrait plus prudent mais
amputerait les années 1950, dont ils représentent près de 60 % des maxima — c'est-à-dire
précisément le point d'appui de toute tendance longue.
"""

import csv
import gzip
import io
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import httpx

DATASET_QUOTIDIEN = "6569b51ae64326786e4e8e1a"
"""« Données climatologiques de base - quotidiennes », publié par Météo-France."""

URL_CATALOGUE = f"https://www.data.gouv.fr/api/1/datasets/{DATASET_QUOTIDIEN}/"

MOTIF_RESSOURCE = "RR-T-Vent"
"""Les fichiers « autres-parametres » ne portent ni TN ni TX : on ne les lit pas."""

QUALITES_RETENUES = frozenset({"1", "9"})

ATTRIBUTION = "Météo-France, données climatologiques de base (licence ouverte LOV2)"


class FormatInattendu(RuntimeError):
    """Le fichier servi n'a pas les colonnes qu'on sait lire."""


@dataclass(frozen=True)
class JourneeMesuree:
    """Un jour d'un Poste, tel que publié : identité du Poste comprise.

    Le fichier répète l'identité du Poste à chaque ligne. On la transporte plutôt que
    de la recharger : elle sert à construire le référentiel des Postes dans le même
    passage, sans second téléchargement.
    """

    poste_numero: str
    nom: str
    latitude: float
    longitude: float
    altitude: float
    jour: date
    tn_c: float | None
    tx_c: float | None

    @property
    def vide(self) -> bool:
        return self.tn_c is None and self.tx_c is None


def _nombre(brut: str | None) -> float | None:
    if not brut:
        return None
    try:
        return float(brut)
    except ValueError:
        return None


def _valeur(ligne: dict, champ: str) -> float | None:
    """La valeur d'un champ, ou None si elle est absente ou de qualité écartée."""
    if ligne.get(f"Q{champ}") not in QUALITES_RETENUES:
        return None
    return _nombre(ligne.get(champ))


CHAMPS_ATTENDUS = ("NUM_POSTE", "NOM_USUEL", "LAT", "LON", "ALTI", "AAAAMMJJ", "TN", "TX")


def lire_csv(flux: io.TextIOBase) -> Iterator[JourneeMesuree]:
    """Convertit un fichier quotidien départemental en Journées mesurées.

    Les lignes sans aucune température exploitable sont écartées ici : un Poste
    pluviométrique seul n'a rien à dire sur les températures, et le fichier en compte
    beaucoup — plus de la moitié des lignes de l'Isère.
    """
    lecteur = csv.DictReader(flux, delimiter=";")
    manquants = [c for c in CHAMPS_ATTENDUS if c not in (lecteur.fieldnames or [])]
    if manquants:
        raise FormatInattendu(
            f"Colonnes absentes du fichier Météo-France : {manquants}. "
            f"Colonnes reçues : {sorted(lecteur.fieldnames or [])}"
        )

    for ligne in lecteur:
        brut_jour = ligne.get("AAAAMMJJ") or ""
        if len(brut_jour) != 8 or not brut_jour.isdigit():
            continue
        latitude, longitude, altitude = (
            _nombre(ligne.get("LAT")),
            _nombre(ligne.get("LON")),
            _nombre(ligne.get("ALTI")),
        )
        if latitude is None or longitude is None or altitude is None:
            continue

        journee = JourneeMesuree(
            poste_numero=ligne["NUM_POSTE"],
            nom=(ligne.get("NOM_USUEL") or "").strip(),
            latitude=latitude,
            longitude=longitude,
            altitude=altitude,
            jour=date(int(brut_jour[:4]), int(brut_jour[4:6]), int(brut_jour[6:8])),
            tn_c=_valeur(ligne, "TN"),
            tx_c=_valeur(ligne, "TX"),
        )
        if not journee.vide:
            yield journee


class ClientClimatologie:
    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=180.0, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def ressources(self, departement: str) -> list[tuple[str, str]]:
        """Les fichiers quotidiens d'un département, du plus ancien au plus récent.

        Retourne des couples (titre, url). Le titre sert aux journaux : c'est lui qui
        dit quelle période a été chargée.
        """
        reponse = self._client.get(URL_CATALOGUE)
        reponse.raise_for_status()
        marque = f"_{departement}_"
        trouvees = [
            (r.get("title", ""), r["url"])
            for r in reponse.json().get("resources", [])
            if marque in r.get("title", "") and MOTIF_RESSOURCE in r.get("title", "")
        ]
        if not trouvees:
            raise FormatInattendu(
                f"Aucun fichier quotidien pour le département {departement} dans le "
                f"catalogue. Vérifiez que le numéro est bien celui d'un département "
                f"français, sur deux ou trois caractères (« 38 », « 2A », « 974 »)."
            )
        return sorted(trouvees)

    def journees(self, departement: str) -> Iterator[JourneeMesuree]:
        """Toutes les Journées mesurées d'un département, tous Postes confondus."""
        for _titre, url in self.ressources(departement):
            reponse = self._client.get(url)
            reponse.raise_for_status()
            with gzip.open(io.BytesIO(reponse.content), "rt", encoding="utf-8") as flux:
                yield from lire_csv(flux)
