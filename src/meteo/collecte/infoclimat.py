"""Récupération des Observations auprès du réseau StatIC (Infoclimat).

Contraintes du service, à respecter scrupuleusement — c'est une association de
bénévoles qui l'offre gratuitement et sans publicité :

- 7 jours consécutifs au maximum par requête ;
- moins d'une requête par seconde, moins de 5 000 par 24 h, sous peine de
  verrouillage (HTTP 509) ;
- jeton nominatif, **lié à une adresse IP déclarée** : la collecte ne fonctionne
  que depuis la machine déclarée, en pratique le VPS et non le poste de dev ;
- attribution obligatoire : un lien vers www.infoclimat.fr doit figurer dans
  toute application exploitant ces données.

Format de la réponse, constaté sur le terrain (juillet 2026) : un objet portant
`status`, `errors`, `stations`, `metadata` et `hourly`. `hourly` associe à chaque code
de Station la liste de ses mesures, plus une clé technique `_params` à ignorer. Les
valeurs sont des chaînes, les horodatages sont en UTC.

Les Stations n'émettent pas à pas horaire mais toutes les 10 ou 15 minutes selon le
matériel. On ne retient que les mesures tombant à la minute 0, seules comparables aux
Prévisions : la température d'Open-Meteo est instantanée à l'heure pile, et sa
précipitation est le cumul de l'heure écoulée — exactement ce que porte `pluie_1h`.
Moyenner les mesures intermédiaires décalerait systématiquement l'Observation par
rapport à ce qu'elle est censée vérifier.
"""

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx

URL = "https://www.infoclimat.fr/opendata/"

JOURS_PAR_APPEL = 7
"""Plafond imposé par le service."""

DELAI_ENTRE_APPELS_S = 1.5
"""Au-dessus de la seconde exigée : on se garde une marge."""

CHAMP_TEMPERATURE = "temperature"
CHAMP_PLUIE = "pluie_1h"
"""Cumul de l'heure écoulée, homologue de la précipitation horaire d'Open-Meteo."""

CHAMP_INSTANT = "dh_utc"


class FormatInattendu(RuntimeError):
    """Le service a répondu autre chose que ce qu'on sait lire."""


@dataclass(frozen=True)
class ValeurObservee:
    station_code: str
    instant: datetime
    temperature_c: float | None
    precipitation_mm: float | None


def _tranches(debut: date, fin: date) -> Iterator[tuple[date, date]]:
    curseur = debut
    while curseur <= fin:
        borne = min(curseur + timedelta(days=JOURS_PAR_APPEL - 1), fin)
        yield curseur, borne
        curseur = borne + timedelta(days=1)


def _nombre(brut: object) -> float | None:
    if brut is None or brut == "":
        return None
    try:
        return float(brut)
    except (TypeError, ValueError):
        return None


def lire_reponse(corps: dict) -> Iterator[ValeurObservee]:
    """Convertit la réponse du service en Observations horaires.

    Le parseur est délibérément strict : à la moindre surprise il lève
    FormatInattendu en affichant ce qu'il a reçu, plutôt que de produire en silence
    des Observations fausses qui pollueraient tous les Verdicts.
    """
    if corps.get("status") != "OK":
        raise RuntimeError(
            f"Infoclimat signale un problème : status={corps.get('status')} "
            f"errors={corps.get('errors')}"
        )

    mesures_par_station = corps.get("hourly")
    if not isinstance(mesures_par_station, dict):
        raise FormatInattendu(
            "Aucune clé « hourly » exploitable dans la réponse Infoclimat. "
            f"Clés reçues : {sorted(corps)}"
        )

    for code, mesures in mesures_par_station.items():
        # « _params » et consorts décrivent la réponse, ils ne sont pas des Stations.
        if code.startswith("_"):
            continue
        if not isinstance(mesures, list):
            raise FormatInattendu(
                f"Les mesures de la station {code} ne sont pas une liste "
                f"mais un {type(mesures).__name__}."
            )
        for mesure in mesures:
            if CHAMP_INSTANT not in mesure:
                raise FormatInattendu(
                    f"Champ « {CHAMP_INSTANT} » absent d'une mesure de la station {code}. "
                    f"Champs reçus : {sorted(mesure)}"
                )
            instant = datetime.fromisoformat(str(mesure[CHAMP_INSTANT])).replace(tzinfo=UTC)
            if instant.minute != 0:
                continue
            yield ValeurObservee(
                station_code=code,
                instant=instant.replace(second=0, microsecond=0),
                temperature_c=_nombre(mesure.get(CHAMP_TEMPERATURE)),
                precipitation_mm=_nombre(mesure.get(CHAMP_PLUIE)),
            )


class ClientInfoclimat:
    def __init__(
        self,
        jeton: str,
        client: httpx.Client | None = None,
        delai_s: float = DELAI_ENTRE_APPELS_S,
    ):
        if not jeton:
            raise ValueError(
                "Aucun jeton Infoclimat. Créez un compte sur https://www.infoclimat.fr/opendata/ "
                "puis renseignez METEO_JETON_INFOCLIMAT. Le jeton est lié à l'adresse IP déclarée."
            )
        self._jeton = jeton
        self._client = client or httpx.Client(timeout=90.0)
        self._delai_s = delai_s
        self._dernier_appel = 0.0

    def close(self) -> None:
        self._client.close()

    def _patienter(self) -> None:
        attente = self._delai_s - (time.monotonic() - self._dernier_appel)
        if attente > 0:
            time.sleep(attente)
        self._dernier_appel = time.monotonic()

    def observations(
        self, codes: list[str], debut: date, fin: date
    ) -> Iterator[ValeurObservee]:
        """Les Observations de plusieurs Stations sur une période, par tranches de 7 jours."""
        for tranche_debut, tranche_fin in _tranches(debut, fin):
            self._patienter()
            reponse = self._client.get(
                URL,
                params=[
                    # version=2 est ce que passe l'interface officielle du site.
                    ("version", "2"),
                    ("method", "get"),
                    ("format", "json"),
                    ("start", tranche_debut.isoformat()),
                    ("end", tranche_fin.isoformat()),
                    ("token", self._jeton),
                    *(("stations[]", c) for c in codes),
                ],
            )
            if reponse.status_code == 509:
                raise RuntimeError(
                    "Infoclimat a verrouillé l'accès pour dépassement de quota. "
                    "Attendez 24 h et espacez davantage les requêtes."
                )
            reponse.raise_for_status()

            texte = reponse.text.strip()
            if not texte.startswith("{"):
                # Le service répond en texte brut sur les erreurs d'authentification
                # (« Could not authenticate request », « Wrong ip address »).
                raise RuntimeError(f"Infoclimat a refusé la requête : {texte[:200]}")

            yield from lire_reponse(reponse.json())
