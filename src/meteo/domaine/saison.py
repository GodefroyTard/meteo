"""Saisons météorologiques.

Découpage en trimestres pleins (décembre-janvier-février pour l'hiver), et non
en saisons astronomiques : c'est celui qui correspond aux régimes de temps.
"""

from datetime import date, timedelta
from enum import StrEnum


class Saison(StrEnum):
    HIVER = "hiver"
    PRINTEMPS = "printemps"
    ETE = "ete"
    AUTOMNE = "automne"

    @property
    def libelle(self) -> str:
        return {
            Saison.HIVER: "en hiver",
            Saison.PRINTEMPS: "au printemps",
            Saison.ETE: "en été",
            Saison.AUTOMNE: "en automne",
        }[self]


_PAR_MOIS = (
    Saison.HIVER, Saison.HIVER, Saison.PRINTEMPS,
    Saison.PRINTEMPS, Saison.PRINTEMPS, Saison.ETE,
    Saison.ETE, Saison.ETE, Saison.AUTOMNE,
    Saison.AUTOMNE, Saison.AUTOMNE, Saison.HIVER,
)


def saison_de(jour: date) -> Saison:
    return _PAR_MOIS[jour.month - 1]


def mois_de(saison: Saison) -> tuple[int, ...]:
    """Les numéros de mois couverts par une saison."""
    return tuple(m for m, s in enumerate(_PAR_MOIS, start=1) if s is saison)


def heures_attendues(debut: date, fin: date, saison: Saison) -> int:
    """Nombre d'heures d'une période tombant dans cette saison.

    C'est le dénominateur de la Couverture : ce qu'on aurait dû mesurer.
    """
    jours = (fin - debut).days + 1
    return 24 * sum(1 for i in range(jours) if saison_de(debut + timedelta(days=i)) is saison)
