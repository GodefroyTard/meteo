"""Vent et indice UV, traduits en mots.

Ces deux mesures ne servent à juger aucun Modèle : elles décrivent la journée, et
c'est tout. Elles n'ont donc ni Verdict ni comparaison — seulement une valeur, un
libellé, et la mention de qui l'annonce.

Comme pour le Temps, aucune couleur ici : la page en réserve deux significations,
le Temps et le Modèle (ADR 0007), et une troisième les brouillerait.
"""

from dataclasses import dataclass

ROSE: tuple[str, ...] = (
    "nord",
    "nord-est",
    "est",
    "sud-est",
    "sud",
    "sud-ouest",
    "ouest",
    "nord-ouest",
)


def provenance(degres: float | None) -> str | None:
    """D'où souffle le vent, en toutes lettres.

    Convention météorologique : l'angle désigne la direction d'où vient le vent,
    0° étant le nord. Un vent à 90° est un vent d'est, il va vers l'ouest.
    """
    if degres is None:
        return None
    return ROSE[round(degres / 45) % 8]


# Bornes hautes, en km/h, et le mot qui va avec.
_FORCES: tuple[tuple[float, str], ...] = (
    (5, "calme"),
    (20, "faible"),
    (39, "modéré"),
    (62, "soutenu"),
    (89, "fort"),
)
_FORCE_EXTREME = "violent"


CRANS_VENT = 6
"""Les six degrés de force, de calme à violent."""


@dataclass(frozen=True)
class Vent:
    vitesse_kmh: float
    rafales_kmh: float | None
    degres: float | None
    provenance: str | None
    """D'où il vient, en toutes lettres. None si la direction n'est pas annoncée."""

    libelle: str
    """Calme, faible, modéré, soutenu, fort, violent."""

    cran: int
    """Degré de force atteint, de 1 à CRANS_VENT."""

    @property
    def vers(self) -> float | None:
        """L'angle vers lequel pointer une flèche : le vent va à l'opposé d'où il vient."""
        return None if self.degres is None else (self.degres + 180) % 360


def vent(vitesse_kmh: float | None, rafales_kmh: float | None, degres: float | None) -> Vent | None:
    if vitesse_kmh is None:
        return None
    cran = next(
        (i for i, (borne, _) in enumerate(_FORCES, 1) if vitesse_kmh < borne), CRANS_VENT
    )
    libelle = next((mot for borne, mot in _FORCES if vitesse_kmh < borne), _FORCE_EXTREME)
    return Vent(vitesse_kmh, rafales_kmh, degres, provenance(degres), libelle, cran)


CRANS_UV = 5
"""Nombre de paliers de l'échelle OMM, du plus faible au plus extrême."""

SEUIL_PROTECTION = 3.0
"""À partir de 3, l'OMS recommande de se protéger. En dessous, on ne dit rien."""

# Bornes hautes de l'échelle OMM, et le mot qui va avec.
_PALIERS_UV: tuple[tuple[float, str], ...] = (
    (3, "faible"),
    (6, "modéré"),
    (8, "fort"),
    (11, "très fort"),
)
_UV_EXTREME = "extrême"


@dataclass(frozen=True)
class Uv:
    indice: float
    libelle: str
    cran: int
    """Palier atteint sur l'échelle, de 1 à CRANS_UV."""

    @property
    def protection(self) -> bool:
        return self.indice >= SEUIL_PROTECTION


def uv(indice: float | None) -> Uv | None:
    if indice is None:
        return None
    for cran, (borne, mot) in enumerate(_PALIERS_UV, start=1):
        if indice < borne:
            return Uv(indice, mot, cran)
    return Uv(indice, _UV_EXTREME, CRANS_UV)


SEUIL_RESSENTI_C = 1.0
"""En deçà, le ressenti ne se distingue pas du thermomètre et on ne dit rien."""


@dataclass(frozen=True)
class Ressenti:
    valeur_c: float
    ecart_c: float
    libelle: str


def ressenti(apparente_c: float | None, reelle_c: float | None) -> Ressenti | None:
    if apparente_c is None:
        return None
    ecart = 0.0 if reelle_c is None else apparente_c - reelle_c
    if abs(ecart) < SEUIL_RESSENTI_C:
        libelle = "comme au thermomètre"
    elif ecart > 0:
        libelle = "plus lourd qu'au thermomètre"
    else:
        libelle = "plus frais qu'au thermomètre"
    return Ressenti(apparente_c, ecart, libelle)


# Bornes hautes d'humidité relative, en pourcent, et le mot qui va avec.
_HUMIDITES: tuple[tuple[float, str], ...] = (
    (35, "air sec"),
    (65, "confortable"),
    (85, "humide"),
)
_HUMIDITE_EXTREME = "très humide"


CRANS_HUMIDITE = 4


@dataclass(frozen=True)
class Humidite:
    pourcent: float
    libelle: str
    cran: int


def humidite(pourcent: float | None) -> Humidite | None:
    if pourcent is None:
        return None
    mot = next((m for borne, m in _HUMIDITES if pourcent < borne), _HUMIDITE_EXTREME)
    cran = next(
        (i for i, (borne, _) in enumerate(_HUMIDITES, 1) if pourcent < borne), CRANS_HUMIDITE
    )
    return Humidite(pourcent, mot, cran)


SEUIL_PRESSION_HPA = 1.0
"""Variation sur trois heures en deçà de laquelle le baromètre est dit stable."""

SEUIL_PRESSION_FORTE_HPA = 3.0
"""Au-delà, la variation est franche : c'est le signe d'un changement rapide."""


@dataclass(frozen=True)
class Pression:
    hpa: float
    variation_hpa: float | None
    """Écart sur trois heures. None quand l'heure de référence manque."""

    libelle: str


def pression(hpa: float | None, il_y_a_trois_heures_hpa: float | None) -> Pression | None:
    """Le baromètre et sa tendance. C'est la tendance qui informe, pas la valeur."""
    if hpa is None:
        return None
    if il_y_a_trois_heures_hpa is None:
        return Pression(hpa, None, "tendance inconnue")

    variation = hpa - il_y_a_trois_heures_hpa
    if abs(variation) < SEUIL_PRESSION_HPA:
        libelle = "stable"
    elif variation > 0:
        libelle = "en forte hausse" if variation >= SEUIL_PRESSION_FORTE_HPA else "en hausse"
    else:
        libelle = "en forte baisse" if -variation >= SEUIL_PRESSION_FORTE_HPA else "en baisse"
    return Pression(hpa, variation, libelle)


@dataclass(frozen=True)
class Isotherme:
    altitude_m: float
    denivele_m: float | None
    """Hauteur au-dessus du lieu. Négatif quand l'isotherme passe sous le lieu."""

    au_dessus: bool

    @property
    def proximite(self) -> str:
        """« sous », « proche » ou « haut » — ce qui décide de l'intensité de la teinte."""
        if self.denivele_m is None:
            return "haut"
        if self.denivele_m < 0:
            return "sous"
        return "proche" if self.denivele_m < ISOTHERME_PROCHE_M else "haut"


ISOTHERME_PROCHE_M = 500.0
"""En deçà, le zéro degré surplombe le lieu d'assez peu pour que ça se remarque."""


def isotherme(altitude_m: float | None, altitude_lieu_m: float | None) -> Isotherme | None:
    """L'altitude du 0 °C, et sa position par rapport au lieu.

    C'est l'indication la plus parlante d'une vallée étagée : la même averse tombe
    en pluie à 220 m et en neige à 1965 m. On ne convertit pas en limite pluie-neige
    — elle se situe quelques centaines de mètres plus bas, mais de combien dépend de
    l'intensité des précipitations, et personne ici ne peut le calculer honnêtement.
    """
    if altitude_m is None:
        return None
    if altitude_lieu_m is None:
        return Isotherme(altitude_m, None, True)
    denivele = altitude_m - altitude_lieu_m
    return Isotherme(altitude_m, denivele, denivele >= 0)


CRANS_AIR = 6
"""Les six paliers de l'indice européen de qualité de l'air."""

# Bornes hautes de l'indice européen, et le mot qui va avec.
_PALIERS_AIR: tuple[tuple[float, str], ...] = (
    (20, "bon"),
    (40, "correct"),
    (60, "moyen"),
    (80, "mauvais"),
    (100, "très mauvais"),
)
_AIR_EXTREME = "extrêmement mauvais"

POLLUANTS: dict[str, str] = {
    "pm2_5": "particules fines",
    "pm10": "poussières",
    "nitrogen_dioxide": "dioxyde d'azote",
    "ozone": "ozone",
    "sulphur_dioxide": "dioxyde de soufre",
}


@dataclass(frozen=True)
class QualiteAir:
    indice: float
    libelle: str
    cran: int
    dominant: str | None
    """Le polluant qui porte l'indice, en toutes lettres."""


def qualite_air(indice: float | None, sous_indices: dict[str, float | None]) -> QualiteAir | None:
    """L'indice européen, son palier, et le polluant qui le tire vers le haut.

    L'indice global est celui du pire polluant : nommer ce polluant, c'est dire ce
    qu'on respire, pas seulement combien.
    """
    if indice is None:
        return None
    mot = next((m for borne, m in _PALIERS_AIR if indice < borne), _AIR_EXTREME)
    cran = next((i for i, (borne, _) in enumerate(_PALIERS_AIR, 1) if indice < borne), CRANS_AIR)

    mesures = {c: v for c, v in sous_indices.items() if v is not None}
    cle = max(mesures, key=lambda c: mesures[c]) if mesures else None
    return QualiteAir(indice, mot, cran, POLLUANTS.get(cle) if cle else None)


CHAUD = "chaud"
FROID = "froid"
NEUTRE = "neutre"


def ton_thermique(ecart_c: float | None, seuil_c: float) -> str:
    """Chaud, froid ou neutre — ce qui décide du pôle de la teinte divergente.

    Le neutre n'est pas une absence de couleur mais une valeur à part entière : une
    journée dans la moyenne mérite d'être vue comme telle, pas d'être coloriée faute
    de mieux.
    """
    if ecart_c is None or abs(ecart_c) < seuil_c:
        return NEUTRE
    return CHAUD if ecart_c > 0 else FROID


# Bornes hautes en °C, et le mot qui va avec. Le doux est au milieu : une échelle
# thermique diverge autour du tempéré, elle ne monte pas d'une seule couleur.
_TONS_TEMPERATURE: tuple[tuple[float, str], ...] = (
    (0, "glacial"),
    (10, "froid"),
    (20, "doux"),
    (28, "chaud"),
)
TORRIDE = "torride"


def ton_temperature(degres_c: float | None) -> str | None:
    """Où se situe une température sur l'échelle du ressenti humain."""
    if degres_c is None:
        return None
    return next((mot for borne, mot in _TONS_TEMPERATURE if degres_c < borne), TORRIDE)
