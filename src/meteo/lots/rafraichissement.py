"""Mise à jour incrémentale déclenchable depuis l'interface.

Rafraîchir, c'est aller chercher les derniers jours de Prévisions et d'Observations
puis recalculer les Verdicts. L'opération dure plusieurs dizaines de secondes et
sollicite deux services extérieurs, dont celui d'une association de bénévoles : elle
tourne donc en tâche de fond, une seule à la fois, et pas plus souvent qu'un intervalle
minimum.

Ce garde-fou n'est pas du confort. Le bouton est exposé à tout visiteur : sans lui,
un rechargement répété de la page suffirait à faire verrouiller notre accès Infoclimat.
"""

import threading
import traceback
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from meteo.lots import backfill, verdicts

JOURS_RAFRAICHIS = 3
"""Fenêtre récente recollectée. Assez large pour rattraper une station qui publie
ses mesures avec du retard, assez étroite pour rester rapide."""

INTERVALLE_MINIMUM = timedelta(minutes=30)


@dataclass
class Etat:
    en_cours: bool = False
    demarre_le: datetime | None = None
    termine_le: datetime | None = None
    previsions: int = 0
    observations: int = 0
    verdicts: int = 0
    erreur: str | None = None
    verrou: threading.Lock = field(default_factory=threading.Lock)

    def instantane(self) -> dict:
        return {
            "en_cours": self.en_cours,
            "demarre_le": self.demarre_le.isoformat() if self.demarre_le else None,
            "termine_le": self.termine_le.isoformat() if self.termine_le else None,
            "previsions": self.previsions,
            "observations": self.observations,
            "verdicts": self.verdicts,
            "erreur": self.erreur,
            "prochain_possible_dans_s": self.attente_restante(),
        }

    def attente_restante(self) -> int:
        if self.termine_le is None:
            return 0
        reste = INTERVALLE_MINIMUM - (datetime.now(UTC) - self.termine_le)
        return max(0, int(reste.total_seconds()))


ETAT = Etat()


class TropTot(RuntimeError):
    """L'intervalle minimum entre deux rafraîchissements n'est pas écoulé."""


class DejaEnCours(RuntimeError):
    pass


def executer() -> dict:
    """La mise à jour incrémentale elle-même, sans thread ni garde-fou.

    C'est la seule définition de « rafraîchir » : les derniers jours recollectés puis
    les Verdicts recalculés. Le bouton d'antan et le lot planifié passent tous deux
    par ici, pour qu'il n'y ait jamais deux fenêtres de collecte différentes.

    Attention : `meteo previsions` et `meteo observations` sans bornes repartent de
    METEO_DEBUT_HISTORIQUE, soit plusieurs heures de collecte. Cette fonction, elle,
    se limite à JOURS_RAFRAICHIS — c'est ce qui la rend planifiable.
    """
    fin = date.today()
    debut = fin - timedelta(days=JOURS_RAFRAICHIS)
    return {
        "previsions": backfill.previsions(debut, fin),
        "observations": backfill.observations(debut, fin),
        # Sans bornes, le recalcul se cale sur la plage réellement observée.
        "verdicts": verdicts.calculer(),
    }


def _executer() -> None:
    try:
        compte = executer()
        ETAT.previsions = compte["previsions"]
        ETAT.observations = compte["observations"]
        ETAT.verdicts = compte["verdicts"]
        ETAT.erreur = None
    except Exception as exc:  # noqa: BLE001 — l'erreur est rapportée, pas avalée
        ETAT.erreur = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    finally:
        ETAT.en_cours = False
        ETAT.termine_le = datetime.now(UTC)


def lancer() -> dict:
    """Démarre un rafraîchissement en tâche de fond.

    Lève DejaEnCours si un rafraîchissement tourne déjà, TropTot si le précédent
    est trop récent.
    """
    with ETAT.verrou:
        if ETAT.en_cours:
            raise DejaEnCours("Un rafraîchissement est déjà en cours.")
        attente = ETAT.attente_restante()
        if attente:
            raise TropTot(
                f"Les données ont été rafraîchies il y a moins de "
                f"{int(INTERVALLE_MINIMUM.total_seconds() // 60)} minutes. "
                f"Réessayez dans {attente // 60 + 1} minute(s)."
            )
        ETAT.en_cours = True
        ETAT.demarre_le = datetime.now(UTC)
        ETAT.erreur = None

    threading.Thread(target=_executer, name="rafraichissement", daemon=True).start()
    return ETAT.instantane()


def etat() -> dict:
    return ETAT.instantane()
