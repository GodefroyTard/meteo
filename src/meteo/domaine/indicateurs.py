"""Indicateurs climatiques fondés sur des comptages, non sur des moyennes.

Une moyenne annuelle bouge peu et se laisse tirer par un changement d'instrument. Un
comptage — combien de nuits sous zéro, combien de jours au-dessus de trente — bouge
beaucoup, se vérifie à la main, et correspond à ce qu'on vit. C'est pourquoi ces
indicateurs disent souvent plus que la température moyenne dont ils dérivent.

Trois familles ici :

- les **franchissements de seuil**, comptés année par année ;
- la **saison sans gel**, entre le dernier gel de printemps et le premier d'automne ;
- les **records**, et leur répartition dans le temps.

Les records demandent une précaution que les deux autres n'ont pas. Sous un climat
stable, chaque année a exactement la même chance de détenir le record d'un jour donné :
la part attendue d'une décennie est donc proportionnelle au nombre d'années qu'elle
apporte, décennies incomplètes comprises. Publier un décompte brut ferait passer pour
un signal ce qui n'est qu'un effet du calendrier — les années 1920 paraîtraient
détenir beaucoup de records de froid simplement parce qu'on les regarde en entier.
Tout est donc normalisé par cette attente, et accompagné du bruit qu'elle admet.

Ce module ne connaît ni base de données ni HTTP.
"""

from dataclasses import dataclass
from datetime import date
from math import sqrt

from meteo.domaine.tendance import JOURS_ANNEE_PLEINE

MI_ANNEE = 182
"""Quantième séparant le gel de printemps de celui d'automne, soit le 1er juillet.
Aucune station de plaine ou de moyenne montagne ne gèle en juillet ; ce partage est
donc sans ambiguïté sous nos latitudes."""

ECARTS_TYPES_BRUIT = 2.0
"""Largeur de la bande de bruit des records, en écarts-types. Deux écarts-types
couvrent environ 95 % de ce que le hasard produit."""


@dataclass(frozen=True)
class Seuil:
    """Un franchissement à compter : quelle variable, dans quel sens, à quelle valeur."""

    cle: str
    nom: str
    variable: str
    """« minima » ou « maxima » — laquelle des deux séries est interrogée."""

    au_dessus: bool
    valeur_c: float
    definition: str
    """La règle en toutes lettres, affichée sous le graphe."""


SEUILS = (
    Seuil(
        cle="gel",
        nom="Jours de gel",
        variable="minima",
        au_dessus=False,
        valeur_c=0.0,
        definition="jours dont la température minimale est passée sous 0 °C",
    ),
    Seuil(
        cle="ete",
        nom="Jours d'été",
        variable="maxima",
        au_dessus=True,
        valeur_c=25.0,
        definition="jours dont la température maximale a atteint 25 °C",
    ),
    Seuil(
        cle="chaleur",
        nom="Jours de forte chaleur",
        variable="maxima",
        au_dessus=True,
        valeur_c=30.0,
        definition="jours dont la température maximale a atteint 30 °C",
    ),
)

PAR_CLE = {s.cle: s for s in SEUILS}


@dataclass(frozen=True)
class AnneeComptee:
    """Le décompte d'une année, et le nombre de journées sur lequel il repose."""

    annee: int
    jours: int
    mesures: int


def compter(
    valeurs: dict[date, float], seuil: Seuil, minimum: int = JOURS_ANNEE_PLEINE
) -> list[AnneeComptee]:
    """Compte, année par année, les journées franchissant le seuil.

    Les années trop lacunaires sont écartées et non extrapolées. Une année à trois cents
    journées mesurées produirait mécaniquement moins de jours de gel qu'une année
    complète : ramener son décompte au prorata inventerait des gels qu'on n'a pas vus,
    et l'afficher tel quel dessinerait une fausse accalmie.
    """
    par_annee: dict[int, list[float]] = {}
    for jour, valeur in valeurs.items():
        par_annee.setdefault(jour.year, []).append(valeur)

    comptees = []
    for annee in sorted(par_annee):
        mesures = par_annee[annee]
        if len(mesures) < minimum:
            continue
        franchies = sum(
            1 for v in mesures if (v >= seuil.valeur_c if seuil.au_dessus else v < seuil.valeur_c)
        )
        comptees.append(AnneeComptee(annee=annee, jours=franchies, mesures=len(mesures)))
    return comptees


@dataclass(frozen=True)
class SaisonSansGel:
    """Ce qui sépare le dernier gel de printemps du premier gel d'automne."""

    annee: int
    dernier_gel: int
    """Quantième du dernier jour de gel avant l'été."""

    premier_gel: int
    """Quantième du premier jour de gel après l'été."""

    @property
    def duree(self) -> int:
        return self.premier_gel - self.dernier_gel


def saisons_sans_gel(
    minima: dict[date, float], minimum: int = JOURS_ANNEE_PLEINE
) -> list[SaisonSansGel]:
    """La saison sans gel de chaque année suffisamment mesurée.

    Une année sans aucun gel de printemps ou sans aucun gel d'automne est omise plutôt
    que bornée au 1er janvier ou au 31 décembre : la saison y déborde de l'année civile,
    et la borner inventerait une date que la mesure ne donne pas. Le cas se produit en
    plaine lors des hivers doux, et il deviendra plus fréquent — c'est en soi le signe
    que cet indicateur atteindra un jour sa limite.
    """
    par_annee: dict[int, list[tuple[int, float]]] = {}
    for jour, valeur in minima.items():
        rang = jour.timetuple().tm_yday
        par_annee.setdefault(jour.year, []).append((rang, valeur))

    saisons = []
    for annee in sorted(par_annee):
        journees = par_annee[annee]
        if len(journees) < minimum:
            continue
        printemps = [r for r, v in journees if v < 0.0 and r <= MI_ANNEE]
        automne = [r for r, v in journees if v < 0.0 and r > MI_ANNEE]
        if not printemps or not automne:
            continue
        saisons.append(
            SaisonSansGel(annee=annee, dernier_gel=max(printemps), premier_gel=min(automne))
        )
    return saisons


@dataclass(frozen=True)
class Record:
    """Le record d'un jour du calendrier, et l'année qui le détient."""

    mois: int
    jour: int
    valeur_c: float
    annee: int


@dataclass(frozen=True)
class PartDecennie:
    """Ce qu'une décennie détient de records, rapporté à ce qu'on en attendrait.

    `indice` vaut 1 quand la décennie détient exactement sa part. `bruit` est la
    demi-largeur de ce que le hasard produit seul, à la même échelle : un indice de 2,3
    dans une bande de ±0,4 est un signal, le même dans une bande de ±2 ne l'est pas.
    """

    decennie: int
    annees: int
    records: int
    attendus: float
    bruit: float

    @property
    def indice(self) -> float:
        return self.records / self.attendus if self.attendus else 0.0

    @property
    def remarquable(self) -> bool:
        return abs(self.indice - 1.0) > self.bruit


def records(valeurs: dict[date, float], au_plus_haut: bool) -> list[Record]:
    """Le record de chaque jour du calendrier, chaud ou froid.

    Le 29 février est traité comme n'importe quel autre jour : son record ne se compare
    qu'aux 29 février, ce qui est correct même si l'échantillon y est quatre fois plus
    mince.
    """
    tenants: dict[tuple[int, int], Record] = {}
    for jour, valeur in valeurs.items():
        cle = (jour.month, jour.day)
        detenteur = tenants.get(cle)
        if detenteur is None or (
            valeur > detenteur.valeur_c if au_plus_haut else valeur < detenteur.valeur_c
        ):
            tenants[cle] = Record(
                mois=jour.month, jour=jour.day, valeur_c=valeur, annee=jour.year
            )
    return [tenants[c] for c in sorted(tenants)]


def parts_par_decennie(valeurs: dict[date, float], tenus: list[Record]) -> list[PartDecennie]:
    """Répartit les records par décennie, rapportés à ce qu'un climat stable donnerait.

    L'attente se calcule jour par jour et non globalement : pour un jour du calendrier
    mesuré n fois, chaque année en lice a une chance sur n de détenir le record. Une
    année qui ne couvre que l'été ne pèse donc que sur les jours d'été, et une décennie
    tronquée n'est pas pénalisée deux fois.

    Le bruit suppose les jours indépendants. Ils ne le sont pas tout à fait — deux jours
    voisins se ressemblent — de sorte que la vraie bande est un peu plus large que celle
    annoncée. L'approximation reste bonne : les 365 jours d'une année ne se réduisent
    pas à une poignée de journées indépendantes.
    """
    en_lice: dict[tuple[int, int], set[int]] = {}
    for jour in valeurs:
        en_lice.setdefault((jour.month, jour.day), set()).add(jour.year)

    attendus: dict[int, float] = {}
    variances: dict[int, float] = {}
    for annees in en_lice.values():
        chance = 1.0 / len(annees)
        for decennie in {(a // 10) * 10 for a in annees}:
            presentes = sum(1 for a in annees if (a // 10) * 10 == decennie)
            probabilite = presentes * chance
            attendus[decennie] = attendus.get(decennie, 0.0) + probabilite
            variances[decennie] = variances.get(decennie, 0.0) + probabilite * (1 - probabilite)

    detenus: dict[int, int] = {}
    for record in tenus:
        decennie = (record.annee // 10) * 10
        detenus[decennie] = detenus.get(decennie, 0) + 1

    toutes = {a for annees in en_lice.values() for a in annees}
    parts = []
    for decennie in sorted(attendus):
        attendu = attendus[decennie]
        parts.append(
            PartDecennie(
                decennie=decennie,
                annees=sum(1 for a in toutes if (a // 10) * 10 == decennie),
                records=detenus.get(decennie, 0),
                attendus=attendu,
                bruit=(ECARTS_TYPES_BRUIT * sqrt(variances[decennie]) / attendu)
                if attendu
                else 0.0,
            )
        )
    return parts
