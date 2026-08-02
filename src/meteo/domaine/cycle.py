"""Le cycle annuel d'un Poste : une courbe par année, du 1er janvier au 31 décembre.

Là où la Tendance regarde un jour à travers les années, le Cycle regarde une année
entière. Superposées, les années dessinent la forme du climat d'un lieu — et l'écart
entre les décennies s'y lit sans qu'on ait à le calculer.

Deux traitements sont indispensables pour que ce soit lisible :

- **le lissage**, sans quoi chaque courbe serait un hérisson. Une moyenne glissante
  centrée sur un mois retire le temps qu'il fait et laisse la saison ;
- **le sous-échantillonnage**, sans quoi cent dix années de mesures quotidiennes
  partiraient dans le navigateur pour dessiner des traits d'un pixel. Après lissage, un
  point tous les cinq jours est indiscernable du tracé complet.

Le 29 février est écarté et les quantièmes des années bissextiles sont décalés d'un jour
après lui : sans cela, une courbe sur quatre serait décalée d'un jour par rapport aux
autres sur les trois quarts de l'année.
"""

import calendar
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta

DEMI_LISSAGE_J = 15
"""Demi-largeur de la moyenne glissante : trente et un jours au total. En dessous, les
courbes restent hérissées et se confondent ; au-dessus, les vagues de chaleur et les
coups de froid disparaissent avec le bruit."""

COUVERTURE_LISSAGE = 0.6
"""Part de la fenêtre qui doit être mesurée pour qu'un point lissé soit produit. Sans
ce garde-fou, une moyenne calculée sur trois jours au bord d'une lacune s'afficherait
avec la même autorité qu'une moyenne sur trente et un."""

PAS_TRACE_J = 5
"""Un point tous les cinq jours, après lissage."""

POINTS_MINIMUM = 20
"""Points exigés pour qu'une année soit tracée, soit une centaine de jours couverts.
Une année ouverte en novembre dessinerait un moignon dans un coin du graphique, et
pourrait pire encore servir de repère de décennie."""

JOURS_AN = 365
"""L'axe est calé sur une année non bissextile."""

# Quantième du premier jour de chaque mois, année non bissextile.
DEBUTS_DE_MOIS = (1, 32, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335)


@dataclass(frozen=True)
class CycleAnnuel:
    """Une année, échantillonnée sur l'axe commun des quantièmes."""

    annee: int
    quantiemes: tuple[int, ...]
    valeurs_c: tuple[float, ...]

    @property
    def complete(self) -> bool:
        """Vrai si l'année couvre au moins onze mois de l'axe.

        L'année en cours ne l'est jamais, et c'est voulu : sa courbe s'arrête au dernier
        jour lissable, ce qui montre honnêtement jusqu'où va la mesure.
        """
        return bool(self.quantiemes) and self.quantiemes[-1] - self.quantiemes[0] > 330


def quantieme(jour: date) -> int | None:
    """Le rang du jour dans une année ramenée à 365 jours, ou None le 29 février."""
    rang = jour.timetuple().tm_yday
    if calendar.isleap(jour.year):
        if jour.month == 2 and jour.day == 29:
            return None
        if rang > 60:
            return rang - 1
    return rang


def moyennes_quotidiennes(
    minima: dict[date, float], maxima: dict[date, float]
) -> dict[date, float]:
    """La demi-somme du minimum et du maximum, jour par jour.

    C'est la définition retenue par Météo-France pour sa colonne TNTXM, et la seule
    disponible ici : le pas horaire n'existe pas dans les Séries longues. Une journée
    dont l'un des deux extrêmes manque est écartée — la moyenne d'un seul extrême
    pencherait systématiquement du même côté.
    """
    return {
        jour: (minima[jour] + maxima[jour]) / 2.0
        for jour in minima.keys() & maxima.keys()
    }


def lisser(
    valeurs: dict[date, float],
    demi_largeur: int = DEMI_LISSAGE_J,
    couverture: float = COUVERTURE_LISSAGE,
) -> dict[date, float]:
    """Moyenne glissante centrée, calculée sur les dates réelles.

    Travailler sur les dates et non sur les quantièmes fait que la fenêtre du 1er janvier
    va chercher la fin décembre précédente, sans traitement particulier. Les points dont
    la fenêtre est trop creuse ne sont pas produits.

    Fenêtre glissante et non recalcul complet à chaque jour : sur les quarante mille
    journées d'un Poste centenaire, la version naïve coûtait une demi-seconde à chaque
    affichage de la page.
    """
    if not valeurs:
        return {}

    exige = max(1, int((2 * demi_largeur + 1) * couverture))
    debut, fin = min(valeurs), max(valeurs)
    serie = [valeurs.get(debut + timedelta(days=i)) for i in range((fin - debut).days + 1)]

    somme, compte = 0.0, 0
    for i in range(min(demi_largeur, len(serie))):
        if serie[i] is not None:
            somme += serie[i]
            compte += 1

    lissees = {}
    for i, valeur in enumerate(serie):
        entrant = i + demi_largeur
        if entrant < len(serie) and serie[entrant] is not None:
            somme += serie[entrant]
            compte += 1

        if valeur is not None and compte >= exige:
            lissees[debut + timedelta(days=i)] = somme / compte

        sortant = i - demi_largeur
        if sortant >= 0 and serie[sortant] is not None:
            somme -= serie[sortant]
            compte -= 1

    return lissees


def cycles(
    valeurs: dict[date, float], pas: int = PAS_TRACE_J, minimum: int = POINTS_MINIMUM
) -> list[CycleAnnuel]:
    """Regroupe des valeurs quotidiennes en une courbe par année, sous-échantillonnée.

    Les années trop peu couvertes sont écartées ici, en amont du choix des décennies :
    un Poste ouvert en novembre 1916 ne doit pas voir ce moignon d'année servir de
    repère au reste du graphique.
    """
    par_annee: dict[int, dict[int, float]] = {}
    for jour, valeur in valeurs.items():
        rang = quantieme(jour)
        if rang is None:
            continue
        par_annee.setdefault(jour.year, {})[rang] = valeur

    resultat = []
    for annee in sorted(par_annee):
        points = par_annee[annee]
        retenus = sorted(r for r in points if r % pas == 1)
        if len(retenus) < minimum:
            continue
        resultat.append(
            CycleAnnuel(
                annee=annee,
                quantiemes=tuple(retenus),
                valeurs_c=tuple(points[r] for r in retenus),
            )
        )
    return resultat


def moyennes_mensuelles(annee: CycleAnnuel) -> tuple[float | None, ...]:
    """Les douze moyennes mensuelles d'une année, à partir des points tracés.

    C'est la contrepartie chiffrée du graphe : sept mille points ne se mettent pas en
    tableau, cent trente-deux moyennes si. Un mois sans point rend None plutôt que zéro.
    """
    seaux: list[list[float]] = [[] for _ in range(12)]
    for rang, valeur in zip(annee.quantiemes, annee.valeurs_c, strict=True):
        mois = bisect_right(DEBUTS_DE_MOIS, rang) - 1
        seaux[mois].append(valeur)
    return tuple(sum(s) / len(s) if s else None for s in seaux)


def decennies(derniere: int, premiere: int) -> list[int]:
    """L'année la plus récente, puis de dix en dix vers le passé.

    L'ancrage est la dernière année et non un multiple rond : la question posée est
    « où en est-on par rapport à il y a dix, vingt, trente ans », pas « que valait
    l'année 1980 ».
    """
    return [annee for annee in range(derniere, premiere - 1, -10)]
