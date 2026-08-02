"""L'enneigement d'un Poste, saison après saison.

La saison de neige va du 1er août au 31 juillet et porte le millésime de son année de
départ : l'hiver 1962-1963 est « la saison 1962 ». La caler sur l'année civile couperait
chaque hiver en son milieu et mêlerait dans un même point le mois de janvier d'un hiver
et le mois de décembre du suivant.

Deux grandeurs, et il faut les deux :

- **les jours de neige au sol** disent la durée de l'enneigement. C'est ce qui compte
  pour la végétation, la faune et l'eau qui descendra au printemps ;
- **l'épaisseur maximale** dit son intensité. Une saison peut être courte et abondante,
  ou longue et maigre.

Elles ne se résument pas l'une l'autre, et elles n'ont pas la même unité — d'où deux
échelles, jamais un seul axe partagé.

La neige est bien plus variable d'une année sur l'autre que la température : en Isère,
seul un Poste sur trois franchit le seuil de significativité sur les jours d'enneigement,
alors que **dix Postes sur dix ont une pente négative**. Le signal est collectif avant
d'être individuel, et la page doit le dire ainsi plutôt que de laisser croire à l'absence
d'évolution là où la significativité manque.

Ce module ne connaît ni base de données ni HTTP.
"""

from dataclasses import dataclass
from datetime import date

MOIS_DEBUT_SAISON = 8
"""Août : aucun Poste isérois n'a de neige au sol à cette date, pas même à 2 970 m."""

JOURS_SAISON_MINIMUM = 300
"""Jours mesurés exigés dans la saison. La hauteur de neige est relevée toute l'année —
un zéro de juillet est une mesure — donc une saison complète en compte 365."""

SEUIL_CM = 0.0
"""Au-dessus, le sol est enneigé. Météo-France relève des centimètres entiers : le
premier centimètre suffit à faire une journée d'enneigement."""


@dataclass(frozen=True)
class SaisonNeige:
    """Un hiver, de son premier flocon au sol au dernier."""

    saison: int
    jours_au_sol: int
    epaisseur_max_cm: float
    premiere: date | None
    derniere: date | None
    fraiche_cm: float | None
    mesures: int

    @property
    def libelle(self) -> str:
        return f"{self.saison}-{self.saison + 1}"

    @property
    def enneigee(self) -> bool:
        return self.jours_au_sol > 0


def saison_de(jour: date) -> int:
    """Le millésime de la saison à laquelle appartient un jour."""
    return jour.year if jour.month >= MOIS_DEBUT_SAISON else jour.year - 1


def saisons(
    hauteurs: dict[date, float],
    fraiches: dict[date, float] | None = None,
    minimum: int = JOURS_SAISON_MINIMUM,
) -> list[SaisonNeige]:
    """Regroupe des hauteurs quotidiennes en saisons.

    Les saisons trop lacunaires sont écartées et non extrapolées : un hiver mesuré à
    moitié compterait mécaniquement moins de jours d'enneigement, et dessinerait un
    recul là où il n'y a qu'un trou dans le relevé.

    Une saison sans un flocon est conservée avec zéro jour : c'est une information, et
    l'omettre gonflerait la moyenne des saisons restantes.
    """
    fraiches = fraiches or {}
    par_saison: dict[int, list[tuple[date, float]]] = {}
    for jour, hauteur in hauteurs.items():
        par_saison.setdefault(saison_de(jour), []).append((jour, hauteur))

    cumuls: dict[int, float] = {}
    for jour, hauteur in fraiches.items():
        cumuls[saison_de(jour)] = cumuls.get(saison_de(jour), 0.0) + hauteur

    retenues = []
    for millesime in sorted(par_saison):
        journees = sorted(par_saison[millesime])
        if len(journees) < minimum:
            continue
        enneigees = [(j, h) for j, h in journees if h > SEUIL_CM]
        retenues.append(
            SaisonNeige(
                saison=millesime,
                jours_au_sol=len(enneigees),
                epaisseur_max_cm=max((h for _, h in journees), default=0.0),
                premiere=enneigees[0][0] if enneigees else None,
                derniere=enneigees[-1][0] if enneigees else None,
                fraiche_cm=cumuls.get(millesime),
                mesures=len(journees),
            )
        )
    return retenues


def rang_dans_saison(jour: date, millesime: int) -> int:
    """Le nombre de jours écoulés depuis le 1er août de la saison.

    Sert d'axe commun : les quantièmes de l'année civile placeraient décembre à droite
    de mars, ce qui casserait la lecture d'un hiver.
    """
    return (jour - date(millesime, MOIS_DEBUT_SAISON, 1)).days
