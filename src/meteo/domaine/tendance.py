"""Tendance d'une Série longue sur un jour de l'année, et refus de la tracer.

Comparer le 2 août 1954 au 2 août 2024 ne dit rien : un jour isolé est du bruit, et
deux jours isolés en sont deux. On agrège donc chaque année sur une fenêtre de quelques
jours autour de la date visée, puis on ajuste une droite sur la suite des années.

La fenêtre est centrée sur la date de l'année considérée, bornes comprises : pour le
3 janvier 2000, elle court du 27 décembre 1999 au 10 janvier 2000. Les jours empruntés
à l'année civile précédente comptent pour l'année visée — c'est la saison qui compte,
pas le calendrier.

Trois garde-fous, dans l'esprit du Verdict qui s'abstient quand la Couverture manque :

- une année ne compte que si la fenêtre est suffisamment remplie ;
- une tendance n'est ajustée qu'au-delà d'un nombre minimal d'années ;
- une pente n'est déclarée non nulle que si son intervalle de confiance exclut zéro.

Ce module ne connaît ni base de données ni HTTP : il prend des couples (jour, valeur)
et rend des nombres.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from math import sqrt

FENETRE_J = 7
"""Demi-largeur de la fenêtre, en jours. Quinze jours par année : assez pour amortir
le bruit d'un jour, assez peu pour rester dans la même saison."""

JOURS_MINIMUM = 8
"""Jours mesurés exigés dans la fenêtre pour qu'une année compte. La majorité des
quinze : une année à deux mesures donnerait un point aussi haut placé que les autres
sur le graphique, sans en valoir le dixième."""

JOURS_ANNEE_PLEINE = 330
"""Jours mesurés à partir desquels une année compte comme pleine dans la couverture
d'un Poste. Trente-cinq jours de tolérance sur trois cent soixante-cinq : une série
climatologique connaît des pannes, elle ne connaît pas de trimestres muets."""

ANNEES_MINIMUM = 30
"""Durée d'une normale climatique au sens de l'OMM. En deçà, on ne trace pas de
tendance : trente ans est la limite reconnue sous laquelle la variabilité naturelle
domine le signal."""

HORIZON_PROJECTION = 2050
"""Terme du prolongement. Au-delà, une droite ajustée sur le passé n'a plus de sens :
les projections climatiques elles-mêmes changent de régime selon les trajectoires
d'émissions, qu'une régression linéaire ignore."""

# Valeur critique de Student à 95 %, bilatérale, par degrés de liberté. La régression
# consomme deux paramètres : df = n - 2, donc df >= 28 dès ANNEES_MINIMUM années.
_T_95 = {28: 2.048, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}
_T_95_ASYMPTOTE = 1.960


def _t_critique(df: int) -> float:
    for seuil in sorted(_T_95):
        if df <= seuil:
            return _T_95[seuil]
    return _T_95_ASYMPTOTE


@dataclass(frozen=True)
class AnneeAgregee:
    """La valeur d'une année sur la fenêtre, et ce qui la soutient."""

    annee: int
    valeur: float
    nb_jours: int


@dataclass(frozen=True)
class Tendance:
    """Une droite ajustée sur des années, avec de quoi la contester.

    `pente_par_decennie` est l'unité dans laquelle se lisent les tendances climatiques.
    `incertitude_par_decennie` en est la demi-largeur à 95 % : une pente de 0,4 ± 0,5
    par décennie ne dit rien, et `significative` le déclare.

    Les grandeurs sont sans unité déclarée : le module ajuste aussi bien des degrés
    qu'un nombre de jours de gel par an. C'est l'appelant qui sait ce qu'il mesure.
    """

    pente_par_decennie: float
    incertitude_par_decennie: float
    r2: float
    ecart_type_residuel: float
    nb_annees: int
    premiere_annee: int
    derniere_annee: int

    annee_pivot: float
    """Moyenne des années ajustées. La droite y est la mieux connue."""

    valeur_pivot: float

    dispersion_annees: float
    """Somme des carrés des écarts des années au pivot. Sert à évaser l'incertitude
    en s'éloignant du pivot : sans elle, la bande serait d'égale largeur en 1950 et
    en 2050."""

    @property
    def significative(self) -> bool:
        """Vrai si l'intervalle de confiance de la pente exclut zéro."""
        return abs(self.pente_par_decennie) > self.incertitude_par_decennie

    @property
    def evolution_totale(self) -> float:
        """Ce que la droite a gagné entre la première et la dernière année ajustée."""
        return self.valeur(self.derniere_annee) - self.valeur(self.premiere_annee)

    def valeur(self, annee: float) -> float:
        return self.valeur_pivot + self.pente_par_decennie * (annee - self.annee_pivot) / 10.0

    def incertitude(self, annee: float) -> float:
        """Demi-largeur à 95 % de la droite elle-même à cette année.

        Elle s'évase en s'éloignant du pivot : c'est ce qui rend un prolongement de
        plus en plus flou à mesure qu'on avance, et c'est exactement ce qu'il faut
        montrer plutôt qu'un trait net jusqu'en 2050.
        """
        if self.dispersion_annees <= 0 or self.nb_annees < 3:
            return 0.0
        t = _t_critique(self.nb_annees - 2)
        ecart = (annee - self.annee_pivot) ** 2 / self.dispersion_annees
        return t * self.ecart_type_residuel * sqrt(1.0 / self.nb_annees + ecart)


def fenetre(annee: int, mois: int, jour: int, demi_largeur: int = FENETRE_J) -> list[date]:
    """Les dates de la fenêtre centrée sur un jour d'une année donnée.

    Le 29 février se replie sur le 28 les années non bissextiles : la fenêtre existe
    tous les ans, sans quoi la série n'aurait de points qu'une année sur quatre.
    """
    try:
        centre = date(annee, mois, jour)
    except ValueError:
        centre = date(annee, mois, jour - 1)
    return [centre + timedelta(days=d) for d in range(-demi_largeur, demi_largeur + 1)]


def agreger(
    valeurs: dict[date, float],
    mois: int,
    jour: int,
    annees: range,
    demi_largeur: int = FENETRE_J,
    jours_minimum: int = JOURS_MINIMUM,
) -> list[AnneeAgregee]:
    """Moyenne, année par année, les valeurs tombant dans la fenêtre.

    Les années trop creuses sont omises et non mises à zéro : une année absente se
    voit comme un trou sur le graphique, une année à zéro se lirait comme un hiver.
    """
    agregees = []
    for annee in annees:
        presentes = [valeurs[j] for j in fenetre(annee, mois, jour, demi_largeur) if j in valeurs]
        if len(presentes) < jours_minimum:
            continue
        agregees.append(
            AnneeAgregee(
                annee=annee,
                valeur=sum(presentes) / len(presentes),
                nb_jours=len(presentes),
            )
        )
    return agregees


def ajuster(annees: list[AnneeAgregee], minimum: int = ANNEES_MINIMUM) -> Tendance | None:
    """Ajuste une droite par moindres carrés, ou refuse.

    Rend None sous `minimum` années, ou si toutes tombent sur la même année — cas où
    la pente n'est pas définie plutôt qu'infinie.
    """
    if len(annees) < minimum:
        return None

    n = len(annees)
    xs = [float(a.annee) for a in annees]
    ys = [a.valeur for a in annees]
    x_moyen = sum(xs) / n
    y_moyen = sum(ys) / n

    sxx = sum((x - x_moyen) ** 2 for x in xs)
    if sxx <= 0:
        return None
    sxy = sum((x - x_moyen) * (y - y_moyen) for x, y in zip(xs, ys, strict=True))

    pente_par_an = sxy / sxx
    residus = [y - (y_moyen + pente_par_an * (x - x_moyen)) for x, y in zip(xs, ys, strict=True)]
    sse = sum(r * r for r in residus)
    syy = sum((y - y_moyen) ** 2 for y in ys)

    # n > 2 est acquis : minimum vaut au moins 3 en pratique, et ANNEES_MINIMUM 30.
    ecart_type = sqrt(sse / (n - 2)) if n > 2 else 0.0
    erreur_pente = ecart_type / sqrt(sxx)
    t = _t_critique(n - 2)

    return Tendance(
        pente_par_decennie=pente_par_an * 10.0,
        incertitude_par_decennie=t * erreur_pente * 10.0,
        r2=(1.0 - sse / syy) if syy > 0 else 0.0,
        ecart_type_residuel=ecart_type,
        nb_annees=n,
        premiere_annee=annees[0].annee,
        derniere_annee=annees[-1].annee,
        annee_pivot=x_moyen,
        valeur_pivot=y_moyen,
        dispersion_annees=sxx,
    )
