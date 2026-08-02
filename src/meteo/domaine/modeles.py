"""Catalogue des Modèles et leur Portée.

Les Portées ne sont pas celles annoncées par les producteurs mais celles réellement
servies par l'API Previous Runs d'Open-Meteo, mesurées le 01/08/2026 sur Grenoble.
Un Modèle peut prévoir à 4 jours sans que ses runs passés soient archivés aussi loin :
c'est l'archive qui fait foi ici, pas la plaquette.
"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Modele:
    cle: str
    """Identifiant Open-Meteo."""

    nom: str
    """Nom affiché à l'utilisateur."""

    maille_km: float

    portee: int
    """Anticipation maximale, en jours."""

    debut_archive: date | None = None
    """Premier jour servi par l'API Previous Runs, quand le Modèle est plus jeune que
    la période observée. None signifie « disponible depuis le début ».

    Un Modèle qui porte cette date ne peut pas entrer dans le peloton principal :
    l'alignement n'ayant lieu qu'aux instants où *tous* ont une valeur, il tronquerait
    l'historique de tous les autres à sa propre date de naissance (ADR 0010).
    """

    def couvre(self, anticipation: int) -> bool:
        return 1 <= anticipation <= self.portee


CATALOGUE: tuple[Modele, ...] = (
    Modele("meteofrance_arome_france_hd", "AROME", 1.5, portee=1),
    Modele("icon_d2", "ICON-D2", 2.0, portee=1),
    Modele("meteofrance_arpege_europe", "ARPEGE", 11.0, portee=3),
    Modele("icon_eu", "ICON-EU", 7.0, portee=4),
    Modele("ecmwf_ifs025", "ECMWF", 25.0, portee=7),
    Modele("gfs_seamless", "GFS", 13.0, portee=7),
    # Modèle par apprentissage d'ECMWF, opérationnel. Ses runs passés ne sont archivés
    # que depuis le 01/03/2025, mesuré le 02/08/2026 : il est donc hors peloton.
    Modele(
        "ecmwf_aifs025_single",
        "AIFS",
        25.0,
        portee=7,
        debut_archive=date(2025, 3, 1),
    ),
)

PAR_CLE: dict[str, Modele] = {m.cle: m for m in CATALOGUE}

ANTICIPATION_MAX: int = max(m.portee for m in CATALOGUE)


def modeles_couvrant(anticipation: int) -> tuple[Modele, ...]:
    """Les Modèles en lice à cette Anticipation.

    Deux Modèles ne sont comparables que sur les Anticipations que tous deux couvrent :
    à J+7 le peloton se réduit à ECMWF et GFS.
    """
    return tuple(m for m in CATALOGUE if m.couvre(anticipation))


def etablis() -> tuple[Modele, ...]:
    """Les Modèles archivés depuis le début, seuls comparables sur toute la période."""
    return tuple(m for m in CATALOGUE if m.debut_archive is None)


def nouveaux() -> tuple[Modele, ...]:
    """Les Modèles trop jeunes pour le peloton principal, du plus ancien au plus récent."""
    return tuple(
        sorted((m for m in CATALOGUE if m.debut_archive is not None), key=lambda m: m.debut_archive)
    )


def debut_fenetre_recente() -> date | None:
    """Le jour à partir duquel tous les Modèles du catalogue existent.

    C'est la borne du second classement : celui qui compare tout le monde, sur une
    fenêtre plus courte, et dont les chiffres ne se comparent pas au premier.
    """
    jeunes = nouveaux()
    return max(m.debut_archive for m in jeunes) if jeunes else None
