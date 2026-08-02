"""Catalogue des Modèles et leur Portée.

Les Portées ne sont pas celles annoncées par les producteurs mais celles réellement
servies par l'API Previous Runs d'Open-Meteo, mesurées le 01/08/2026 sur Grenoble.
Un Modèle peut prévoir à 4 jours sans que ses runs passés soient archivés aussi loin :
c'est l'archive qui fait foi ici, pas la plaquette.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Modele:
    cle: str
    """Identifiant Open-Meteo."""

    nom: str
    """Nom affiché à l'utilisateur."""

    maille_km: float

    portee: int
    """Anticipation maximale, en jours."""

    def couvre(self, anticipation: int) -> bool:
        return 1 <= anticipation <= self.portee


CATALOGUE: tuple[Modele, ...] = (
    Modele("meteofrance_arome_france_hd", "AROME", 1.5, portee=1),
    Modele("icon_d2", "ICON-D2", 2.0, portee=1),
    Modele("meteofrance_arpege_europe", "ARPEGE", 11.0, portee=3),
    Modele("icon_eu", "ICON-EU", 7.0, portee=4),
    Modele("ecmwf_ifs025", "ECMWF", 25.0, portee=7),
    Modele("gfs_seamless", "GFS", 13.0, portee=7),
)

PAR_CLE: dict[str, Modele] = {m.cle: m for m in CATALOGUE}

ANTICIPATION_MAX: int = max(m.portee for m in CATALOGUE)


def modeles_couvrant(anticipation: int) -> tuple[Modele, ...]:
    """Les Modèles en lice à cette Anticipation.

    Deux Modèles ne sont comparables que sur les Anticipations que tous deux couvrent :
    à J+7 le peloton se réduit à ECMWF et GFS.
    """
    return tuple(m for m in CATALOGUE if m.couvre(anticipation))
