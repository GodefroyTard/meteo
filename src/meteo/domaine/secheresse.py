"""Sécheresse météorologique : ce que la saison reçoit face à ce qu'elle réclame.

La sécheresse d'ici ne se lit pas dans la pluie. Sur les Séries longues de l'Isère, le
cumul annuel, le cumul d'été, le nombre de jours secs et la plus longue série sèche ne
montrent aucune tendance significative. Ce qui bouge, c'est la **demande** : à
Grenoble-Saint-Geoirs, l'évapotranspiration de mai à septembre gagne 120 mm en
cinquante-six ans, et le bilan s'y creuse de 215 mm.

D'où le choix de mesurer un **bilan** et non un cumul : l'apport moins la demande, sur
la saison où le manque se paie. Hors saison, un déficit ne veut rien dire — il pleut
moins en janvier, mais rien ne pousse et rien n'évapore.

L'indice est standardisé **par les rangs**, non par ajustement d'une loi. Avec cinquante
à cent années, la distribution empirique est mieux connue que n'importe quelle famille
paramétrique qu'on lui imposerait, et le résultat ne dépend d'aucune hypothèse. La
contrepartie doit être dite : un indice ainsi construit ne peut pas sortir de
l'échantillon. Sur n années, la plus sèche vaut au mieux Φ⁻¹(0,44/(n+0,12)) — environ
−2,3 pour cinquante ans. Une sécheresse inédite ne peut donc pas être signalée comme
telle ; elle sera simplement la plus sèche connue.

Ce module ne connaît ni base de données ni HTTP.
"""

from dataclasses import dataclass
from datetime import date
from statistics import NormalDist

from meteo.domaine.tendance import ANNEES_MINIMUM

MOIS_SAISON = (5, 9)
"""Mai à septembre inclus. La saison où la demande évaporative culmine et où le déficit
se traduit en effets visibles — l'herbe qui grille, les débits qui tombent."""

JOURS_SAISON = sum(
    (date(2001, m + 1, 1) - date(2001, m, 1)).days
    for m in range(MOIS_SAISON[0], MOIS_SAISON[1] + 1)
)
"""153 jours, année non bissextile."""

COUVERTURE_SAISON = 0.95
"""Part de la saison qui doit être mesurée. Bien plus exigeante que pour un comptage :
un cumul est une somme, et cinq jours de pluie manquants sur cent cinquante-trois
retirent directement leurs millimètres du total sans que rien ne le signale."""

# Bornes de l'échelle standardisée, du plus sec au plus humide. Ce sont celles de
# l'indice de précipitations standardisé, reprises telles quelles : la page gagne à
# parler la même langue que la littérature plutôt qu'à inventer ses propres seuils.
CLASSES = (
    ("extremement_sec", "Extrêmement sec", None, -2.0),
    ("severement_sec", "Sévèrement sec", -2.0, -1.5),
    ("moderement_sec", "Modérément sec", -1.5, -1.0),
    ("normal", "Dans la normale", -1.0, 1.0),
    ("moderement_humide", "Modérément humide", 1.0, 1.5),
    ("tres_humide", "Très humide", 1.5, 2.0),
    ("extremement_humide", "Extrêmement humide", 2.0, None),
)

SEUIL_SEC = -1.0
"""En deçà, l'année est comptée comme sèche."""


@dataclass(frozen=True)
class BilanSaison:
    """Ce qu'une saison a reçu, ce qu'elle a réclamé, et ce qu'il en reste."""

    annee: int
    apport_mm: float
    demande_mm: float
    jours: int

    @property
    def bilan_mm(self) -> float:
        return self.apport_mm - self.demande_mm


@dataclass(frozen=True)
class EtatSec:
    """Une saison située sur l'échelle standardisée."""

    annee: int
    bilan_mm: float
    indice: float
    classe: str
    libelle: str

    @property
    def sec(self) -> bool:
        return self.indice <= SEUIL_SEC


def _cumul(valeurs: dict[date, float], annee: int, mois: tuple[int, int]) -> tuple[float, int]:
    total, jours = 0.0, 0
    for jour, valeur in valeurs.items():
        if jour.year == annee and mois[0] <= jour.month <= mois[1]:
            total += valeur
            jours += 1
    return total, jours


def bilans(
    apports: dict[date, float],
    demandes: dict[date, float],
    mois: tuple[int, int] = MOIS_SAISON,
    couverture: float = COUVERTURE_SAISON,
) -> list[BilanSaison]:
    """Le bilan de chaque saison suffisamment mesurée, des deux côtés.

    Une saison n'est retenue que si l'apport **et** la demande sont couverts : un bilan
    calculé sur une pluie complète et une évapotranspiration trouée paraîtrait
    excédentaire alors qu'il ne serait qu'incomplet.
    """
    exiges = int(JOURS_SAISON * couverture)
    annees = {j.year for j in apports} & {j.year for j in demandes}

    retenus = []
    for annee in sorted(annees):
        apport, jours_apport = _cumul(apports, annee, mois)
        demande, jours_demande = _cumul(demandes, annee, mois)
        if jours_apport < exiges or jours_demande < exiges:
            continue
        retenus.append(
            BilanSaison(
                annee=annee,
                apport_mm=apport,
                demande_mm=demande,
                jours=min(jours_apport, jours_demande),
            )
        )
    return retenus


def classe_de(indice: float) -> tuple[str, str]:
    """La classe d'un indice, et son libellé."""
    for cle, libelle, bas, haut in CLASSES:
        if (bas is None or indice > bas) and (haut is None or indice <= haut):
            return cle, libelle
    return "normal", "Dans la normale"


def standardiser(
    valeurs: list[BilanSaison], minimum: int = ANNEES_MINIMUM
) -> list[EtatSec]:
    """Place chaque saison sur l'échelle standardisée, par son rang.

    Position de tracé de Gringorten, puis quantile de la loi normale : c'est la méthode
    non paramétrique usuelle, et elle a l'avantage de ne rien supposer d'une
    distribution de bilans hydriques, qui n'est ni normale ni gamma.

    Rend une liste vide sous `minimum` années : un indice standardisé sur vingt valeurs
    prétendrait distinguer des degrés de rareté que vingt valeurs ne connaissent pas.
    """
    n = len(valeurs)
    if n < minimum:
        return []

    normale = NormalDist()
    rangs = {b.annee: i for i, b in enumerate(sorted(valeurs, key=lambda b: b.bilan_mm), 1)}

    etats = []
    for bilan in valeurs:
        position = (rangs[bilan.annee] - 0.44) / (n + 0.12)
        indice = normale.inv_cdf(position)
        cle, libelle = classe_de(indice)
        etats.append(
            EtatSec(
                annee=bilan.annee,
                bilan_mm=bilan.bilan_mm,
                indice=indice,
                classe=cle,
                libelle=libelle,
            )
        )
    return etats


@dataclass(frozen=True)
class FrequenceDecennie:
    """Combien de saisons sèches une décennie a comptées, sur celles qu'elle apporte."""

    decennie: int
    annees: int
    seches: int

    @property
    def part(self) -> float:
        return self.seches / self.annees if self.annees else 0.0


def frequences(etats: list[EtatSec]) -> list[FrequenceDecennie]:
    """La fréquence des saisons sèches par décennie.

    Rapportée au nombre d'années que la décennie apporte, et non à un décompte brut :
    les décennies de bord sont tronquées, et les comparer en valeur absolue ferait
    passer leur brièveté pour une accalmie.
    """
    par_decennie: dict[int, list[EtatSec]] = {}
    for etat in etats:
        par_decennie.setdefault((etat.annee // 10) * 10, []).append(etat)
    return [
        FrequenceDecennie(
            decennie=decennie,
            annees=len(lot),
            seches=sum(1 for e in lot if e.sec),
        )
        for decennie, lot in sorted(par_decennie.items())
    ]
