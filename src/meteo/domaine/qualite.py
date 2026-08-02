"""Garde-fous sur les Observations.

Le réseau participatif produit des mesures défaillantes : capteur en panne qui répète
la même valeur, pic de rayonnement sur un abri mal ventilé, pluviomètre bouché. Sans
filtrage, le Modèle jugé le plus fiable finirait par être celui qui ressemble le plus
aux défauts du capteur.

Trois règles mécaniques suffisent. On ne cherche pas à corriger les Observations
douteuses, seulement à les écarter — et si trop sont écartées, la case de Verdict
n'est pas publiée (voir Couverture).

Ces règles ne voient pas les défauts d'exposition, et il faut distinguer deux cas.
Un décalage constant — station systématiquement trop chaude de 1 °C — pénalise tous
les Modèles pareillement : il fausse l'Écart affiché, pas le classement. Une amplitude
excessive, en revanche, fausse aussi le classement : une Station qui exagère son cycle
jour/nuit favorise les Modèles qui exagèrent le leur.

Le second cas se repère en comparant la signature horaire d'une Station à celle de ses
voisines de même altitude, ce que ces règles locales ne font pas. Le collège de Vizille
en est un exemple mesuré : +2,1 °C de biais à 6 h contre −2,0 °C à 18 h, quand
Saint-Martin-d'Hères, 77 m plus bas, reste neutre en journée.
"""

from dataclasses import dataclass

TEMPERATURE_MIN_C = -40.0
TEMPERATURE_MAX_C = 50.0
PRECIPITATION_MAX_MM_H = 150.0

VARIATION_HORAIRE_MAX_C = 12.0
"""Au-delà, la mesure est tenue pour un artefact et non pour un coup de foehn."""

PAS_IDENTIQUES_MAX = 6
"""Nombre de mesures horaires strictement identiques tolérées avant de conclure
que le capteur est figé."""

COUVERTURE_MINIMALE = 0.6
"""Proportion d'Observations valides en dessous de laquelle on refuse de conclure."""


@dataclass(frozen=True)
class MesureBrute:
    """Une Observation telle que reçue, avant validation."""

    temperature_c: float | None
    precipitation_mm: float | None


def _bornes_respectees(m: MesureBrute) -> bool:
    if m.temperature_c is not None and not (
        TEMPERATURE_MIN_C <= m.temperature_c <= TEMPERATURE_MAX_C
    ):
        return False
    if m.precipitation_mm is not None and not (0.0 <= m.precipitation_mm <= PRECIPITATION_MAX_MM_H):
        return False
    return True


def valider(mesures: list[MesureBrute]) -> list[bool]:
    """Marque chaque mesure d'une série horaire comme exploitable ou non.

    La série doit être ordonnée chronologiquement et à pas horaire régulier, trous
    compris (une heure manquante est une MesureBrute dont les champs valent None).
    """
    valides = [_bornes_respectees(m) for m in mesures]

    # Capteur figé : une même température répétée trop longtemps. Les précipitations
    # sont exclues de cette règle — zéro pendant des jours est le cas normal.
    debut = 0
    for i in range(1, len(mesures) + 1):
        fini = i == len(mesures)
        rupture = fini or mesures[i].temperature_c != mesures[debut].temperature_c
        if rupture:
            longueur = i - debut
            if mesures[debut].temperature_c is not None and longueur > PAS_IDENTIQUES_MAX:
                for j in range(debut, i):
                    valides[j] = False
            debut = i

    # Variation horaire impossible : on écarte les deux mesures encadrant le saut,
    # faute de savoir laquelle des deux ment. La règle ne s'applique qu'entre deux
    # mesures déjà retenues — sauter depuis une valeur aberrante déjà écartée ne
    # dit rien de sa voisine.
    for i in range(1, len(mesures)):
        if not (valides[i - 1] and valides[i]):
            continue
        a, b = mesures[i - 1].temperature_c, mesures[i].temperature_c
        if a is not None and b is not None and abs(b - a) > VARIATION_HORAIRE_MAX_C:
            valides[i - 1] = valides[i] = False

    return valides


def couverture(nb_valides: int, nb_attendues: int) -> float:
    return nb_valides / nb_attendues if nb_attendues else 0.0


def publiable(nb_valides: int, nb_attendues: int) -> bool:
    return couverture(nb_valides, nb_attendues) >= COUVERTURE_MINIMALE
