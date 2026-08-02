"""Récupération des Séries longues auprès de Météo-France (data.gouv.fr).

Le jeu « Données climatologiques de base - quotidiennes » publie, par département, deux
fichiers complémentaires :

- **RR-T-Vent** porte les minima, les maxima et la pluie. C'est le socle : il remonte à
  1950, et bien avant pour les Postes anciens ;
- **autres-parametres** porte l'évapotranspiration potentielle et la neige au sol.
  L'évapotranspiration y vient sous deux formes.
  `ETPMON` est calculée par Penman-Monteith depuis les mesures du Poste ; `ETPGRILLE`
  est interpolée sur une grille. La première est rare — cinq Postes en Isère — la
  seconde couvre quarante-six Postes. Elles ne valent pas la même chose et sont donc
  stockées séparément (ADR 0009).

L'Isère entière tient dans 25 Mo compressés, sans jeton ni quota : on télécharge le
département en entier plutôt que d'interroger poste par poste.

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
précisément le point d'appui de toute tendance longue. `ETPGRILLE` n'est d'ailleurs
servie qu'en qualité 9, ce qui est cohérent avec un produit d'analyse.
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

FAMILLE_TEMPERATURES = "RR-T-Vent"
FAMILLE_AUTRES = "autres-parametres"

QUALITES_RETENUES = frozenset({"1", "9"})

ATTRIBUTION = "Météo-France, données climatologiques de base (licence ouverte LOV2)"

COLONNES = {
    "TN": "tn_c",
    "TX": "tx_c",
    "RR": "rr_mm",
    "ETPMON": "etp_monteith_mm",
    "ETPGRILLE": "etp_grille_mm",
    "NEIGETOTX": "neige_cm",
    "HNEIGEF": "neige_fraiche_cm",
}
"""Colonne du fichier → champ de la Journée mesurée."""

MESURES_TEMPERATURES = ("TN", "TX", "RR")
MESURES_AUTRES = ("ETPMON", "ETPGRILLE", "NEIGETOTX", "HNEIGEF")

CHAMPS_IDENTITE = ("NUM_POSTE", "NOM_USUEL", "LAT", "LON", "ALTI", "AAAAMMJJ")


class FormatInattendu(RuntimeError):
    """Le fichier servi n'a pas les colonnes qu'on sait lire."""


@dataclass(frozen=True)
class JourneeMesuree:
    """Un jour d'un Poste, tel que publié : identité du Poste comprise.

    Le fichier répète l'identité du Poste à chaque ligne. On la transporte plutôt que
    de la recharger : elle sert à construire le référentiel des Postes dans le même
    passage, sans second téléchargement.

    Toutes les mesures sont facultatives. Une passe ne remplit que les colonnes de sa
    famille de fichiers, et les deux passes se rejoignent en base sur la même clé.
    """

    poste_numero: str
    nom: str
    latitude: float
    longitude: float
    altitude: float
    jour: date
    tn_c: float | None = None
    tx_c: float | None = None
    rr_mm: float | None = None
    etp_monteith_mm: float | None = None
    etp_grille_mm: float | None = None
    neige_cm: float | None = None
    neige_fraiche_cm: float | None = None

    @property
    def vide(self) -> bool:
        return all(
            getattr(self, champ) is None for champ in COLONNES.values()
        )


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


def lire_csv(flux: io.TextIOBase, mesures: tuple[str, ...]) -> Iterator[JourneeMesuree]:
    """Convertit un fichier départemental en Journées mesurées.

    `mesures` dit quelles colonnes lire : les deux familles de fichiers partagent leur
    en-tête d'identité et ne diffèrent que par là.

    Les lignes sans aucune mesure exploitable sont écartées ici. Le fichier en compte
    beaucoup : un Poste équipé d'un seul instrument remplit une colonne sur cinq.
    """
    lecteur = csv.DictReader(flux, delimiter=";")
    presentes = set(lecteur.fieldnames or [])
    manquants = [c for c in (*CHAMPS_IDENTITE, *mesures) if c not in presentes]
    if manquants:
        raise FormatInattendu(
            f"Colonnes absentes du fichier Météo-France : {manquants}. "
            f"Colonnes reçues : {sorted(presentes)}"
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
            **{COLONNES[c]: _valeur(ligne, c) for c in mesures},
        )
        if not journee.vide:
            yield journee


class ClientClimatologie:
    def __init__(self, client: httpx.Client | None = None):
        self._client = client or httpx.Client(timeout=180.0, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def ressources(self, departement: str, famille: str) -> list[tuple[str, str]]:
        """Les fichiers d'un département pour une famille, du plus ancien au plus récent.

        Retourne des couples (titre, url). Le titre sert aux journaux : c'est lui qui
        dit quelle période a été chargée.
        """
        reponse = self._client.get(URL_CATALOGUE)
        reponse.raise_for_status()
        marque = f"_{departement}_"
        trouvees = [
            (r.get("title", ""), r["url"])
            for r in reponse.json().get("resources", [])
            if marque in r.get("title", "") and famille in r.get("title", "")
        ]
        if not trouvees:
            raise FormatInattendu(
                f"Aucun fichier « {famille} » pour le département {departement} dans le "
                f"catalogue. Vérifiez que le numéro est bien celui d'un département "
                f"français, sur deux ou trois caractères (« 38 », « 2A », « 974 »)."
            )
        return sorted(trouvees)

    def mesures(
        self, departement: str, famille: str, colonnes: tuple[str, ...]
    ) -> Iterator[JourneeMesuree]:
        """Toutes les Journées d'une famille de fichiers, tous Postes confondus."""
        for _titre, url in self.ressources(departement, famille):
            reponse = self._client.get(url)
            reponse.raise_for_status()
            with gzip.open(io.BytesIO(reponse.content), "rt", encoding="utf-8") as flux:
                yield from lire_csv(flux, colonnes)

    def journees(self, departement: str) -> Iterator[JourneeMesuree]:
        """Températures et pluie."""
        return self.mesures(departement, FAMILLE_TEMPERATURES, MESURES_TEMPERATURES)

    def evapotranspirations(self, departement: str) -> Iterator[JourneeMesuree]:
        """Évapotranspiration potentielle, sous ses deux formes."""
        return self.mesures(departement, FAMILLE_AUTRES, MESURES_AUTRES)
