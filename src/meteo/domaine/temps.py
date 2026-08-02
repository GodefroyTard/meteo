"""Le Temps qu'un Modèle annonce : dégagé, couvert, pluie, orage.

Open-Meteo le rend sous forme de code WMO 4677. Ce module le traduit en trois
choses affichables — une famille, un libellé, une icône — et rien d'autre : aucune
E/S, aucune couleur. Les couleurs sont dans la feuille de style, indexées sur la
famille (ADR 0007).

Tous les Modèles n'annoncent pas de Temps : AROME n'en fournit aucun. Un code
absent donne la famille `inconnu`, et l'interface le dit plutôt que d'inventer un
ciel dégagé au motif qu'il ne pleut pas.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Temps:
    famille: str
    """Regroupement grossier — ce qui détermine la couleur du ciel et l'icône."""

    libelle: str
    """Ce qui est écrit à l'utilisateur, en toutes lettres."""

    icone: str
    """Clé du symbole SVG, telle que déclarée dans le gabarit d'icônes."""


CLAIR = "clair"
VOILE = "voile"
COUVERT = "couvert"
BROUILLARD = "brouillard"
BRUINE = "bruine"
PLUIE = "pluie"
AVERSE = "averse"
NEIGE = "neige"
ORAGE = "orage"
INCONNU = "inconnu"

# (famille, libellé) par code WMO. L'icône se déduit de la famille, sauf pour les
# ciels sans précipitation où elle dépend aussi du jour ou de la nuit.
_CODES: dict[int, tuple[str, str]] = {
    0: (CLAIR, "Ciel dégagé"),
    1: (VOILE, "Peu nuageux"),
    2: (VOILE, "Partiellement nuageux"),
    3: (COUVERT, "Ciel couvert"),
    45: (BROUILLARD, "Brouillard"),
    48: (BROUILLARD, "Brouillard givrant"),
    51: (BRUINE, "Bruine faible"),
    53: (BRUINE, "Bruine"),
    55: (BRUINE, "Bruine dense"),
    56: (BRUINE, "Bruine verglaçante"),
    57: (BRUINE, "Bruine verglaçante dense"),
    61: (PLUIE, "Pluie faible"),
    63: (PLUIE, "Pluie"),
    65: (PLUIE, "Forte pluie"),
    66: (PLUIE, "Pluie verglaçante"),
    67: (PLUIE, "Forte pluie verglaçante"),
    71: (NEIGE, "Neige faible"),
    73: (NEIGE, "Neige"),
    75: (NEIGE, "Fortes chutes de neige"),
    77: (NEIGE, "Grésil"),
    80: (AVERSE, "Averses éparses"),
    81: (AVERSE, "Averses"),
    82: (AVERSE, "Averses violentes"),
    85: (NEIGE, "Averses de neige"),
    86: (NEIGE, "Fortes averses de neige"),
    95: (ORAGE, "Orage"),
    96: (ORAGE, "Orage avec grêle"),
    99: (ORAGE, "Orage avec forte grêle"),
}

_ICONES: dict[str, str] = {
    COUVERT: "couvert",
    BROUILLARD: "brouillard",
    BRUINE: "bruine",
    PLUIE: "pluie",
    AVERSE: "averse",
    NEIGE: "neige",
    ORAGE: "orage",
    INCONNU: "inconnu",
}

_ICONES_JOUR = {CLAIR: "soleil", VOILE: "soleil-voile"}
_ICONES_NUIT = {CLAIR: "lune", VOILE: "lune-voile"}

NON_ANNONCE = Temps(INCONNU, "Temps non annoncé", "inconnu")
"""Ce que rend un Modèle qui ne dit rien du ciel. Affiché tel quel, jamais deviné."""


def temps_de(code: int | None, jour: bool = True) -> Temps:
    """Le Temps correspondant à un code WMO, de jour ou de nuit.

    Un code inconnu du barème est traité comme une absence : mieux vaut afficher
    « temps non annoncé » qu'un libellé faux si l'OMM ajoute un code.
    """
    if code is None or code not in _CODES:
        return NON_ANNONCE

    famille, libelle = _CODES[code]
    table = _ICONES_JOUR if jour else _ICONES_NUIT
    return Temps(famille, libelle, table.get(famille) or _ICONES[famille])


def pleut(temps: Temps) -> bool:
    """Vrai si le Temps annoncé mouille — sert à teinter les heures concernées."""
    return temps.famille in (BRUINE, PLUIE, AVERSE, NEIGE, ORAGE)
