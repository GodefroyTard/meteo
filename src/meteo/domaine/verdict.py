"""Calcul d'un Verdict : quel Modèle croire, et lesquels sont Ex aequo.

Deux façons de se tromper, selon la variable :

- température — un Écart, en degrés, dont on tire un écart moyen et un Biais ;
- pluie — une question binaire, dont on tire un taux d'erreur, décomposé en
  Fausses alertes et Pluies manquées.

Comment l'Ex aequo est tranché
------------------------------
On compare les Modèles sur la *différence appariée* de leurs Écarts, jour par jour,
et non sur le recouvrement de leurs fourchettes prises séparément.

C'est essentiel : la variabilité d'un jour à l'autre écrase de très loin la différence
entre deux Modèles. Deux fourchettes calculées isolément se recouvriraient presque
toujours, et le produit ne dirait jamais rien. En rééchantillonnant les mêmes jours
pour tous les Modèles, la difficulté propre à chaque journée s'annule et il ne reste
que ce qui les sépare vraiment.

Le rééchantillonnage porte sur des journées entières, pas sur des heures isolées :
un Modèle qui se trompe à 14 h se trompe encore à 15 h, et traiter ces heures comme
indépendantes ferait conclure à des différences qui n'existent pas.
"""

from dataclasses import dataclass

import numpy as np

SEUIL_PLUIE_MM = 0.2
"""Hauteur horaire à partir de laquelle on considère qu'il a plu.

Valeur provisoire : à 0,1 mm on compte la bruine et les Fausses alertes explosent,
à 1 mm on ignore ce que les gens appellent de la pluie.
"""

NB_TIRAGES = 1000
GRAINE = 20240204
"""Graine fixe : deux exécutions du même lot doivent produire le même Verdict."""

NIVEAU_CONFIANCE = 95.0


@dataclass(frozen=True)
class ScoreModele:
    modele: str
    ecart_moyen: float
    """Écart moyen en °C, ou taux d'erreur entre 0 et 1 pour la pluie."""

    biais: float | None
    """Positif : le Modèle surestime. None pour la pluie."""

    fausses_alertes: float | None
    """Part des heures annoncées pluvieuses restées sèches. None pour la température."""

    pluies_manquees: float | None
    """Part des heures pluvieuses non annoncées. None pour la température."""

    ex_aequo: bool
    """Indistinguable du meilleur compte tenu du volume de mesures."""


@dataclass(frozen=True)
class Comparaison:
    scores: tuple[ScoreModele, ...]
    """Triés du meilleur au pire."""

    nb_heures: int
    nb_jours: int

    @property
    def vainqueurs(self) -> tuple[str, ...]:
        """Le meilleur Modèle et ceux dont on ne peut pas le distinguer."""
        return tuple(s.modele for s in self.scores if s.ex_aequo)


def il_a_plu(precipitation_mm: np.ndarray, seuil: float = SEUIL_PLUIE_MM) -> np.ndarray:
    return precipitation_mm >= seuil


def _moyennes_reechantillonnees(
    jours: np.ndarray, erreurs: np.ndarray, nb_tirages: int
) -> tuple[np.ndarray, np.ndarray]:
    """Agrège les erreurs par journée puis rééchantillonne les journées avec remise.

    `erreurs` a la forme (nb_heures, nb_modeles). Retourne les moyennes observées
    (nb_modeles,) et les moyennes rééchantillonnées (nb_tirages, nb_modeles).
    """
    _, index = np.unique(jours, return_inverse=True)
    nb_jours = int(index.max()) + 1
    nb_modeles = erreurs.shape[1]

    sommes = np.zeros((nb_jours, nb_modeles))
    np.add.at(sommes, index, erreurs)
    comptes = np.bincount(index, minlength=nb_jours).astype(float)

    observees = sommes.sum(axis=0) / comptes.sum()

    rng = np.random.default_rng(GRAINE)
    tirages = rng.integers(0, nb_jours, size=(nb_tirages, nb_jours))
    sommes_tirees = sommes[tirages].sum(axis=1)
    comptes_tires = comptes[tirages].sum(axis=1)
    return observees, sommes_tirees / comptes_tires[:, None]


def _ex_aequo_avec_meilleur(
    moyennes_tirees: np.ndarray, i_meilleur: int, niveau: float
) -> np.ndarray:
    """Un Modèle est Ex aequo si sa différence au meilleur peut être nulle."""
    differences = moyennes_tirees - moyennes_tirees[:, [i_meilleur]]
    marge = (100.0 - niveau) / 2.0
    bas, haut = np.percentile(differences, [marge, 100.0 - marge], axis=0)
    return (bas <= 0.0) & (0.0 <= haut)


def comparer_temperature(
    jours: np.ndarray,
    previsions: dict[str, np.ndarray],
    observations: np.ndarray,
    nb_tirages: int = NB_TIRAGES,
) -> Comparaison:
    """Compare des Modèles sur la température.

    Toutes les séries doivent être alignées sur les mêmes heures, déjà filtrées de
    leurs Observations douteuses. `jours` porte le numéro de journée de chaque heure.
    """
    noms = list(previsions)
    ecarts = np.column_stack([previsions[n] - observations for n in noms])
    absolus = np.abs(ecarts)

    observees, tirees = _moyennes_reechantillonnees(jours, absolus, nb_tirages)
    i_meilleur = int(np.argmin(observees))
    ex_aequo = _ex_aequo_avec_meilleur(tirees, i_meilleur, NIVEAU_CONFIANCE)
    biais = ecarts.mean(axis=0)

    scores = [
        ScoreModele(
            modele=nom,
            ecart_moyen=float(observees[i]),
            biais=float(biais[i]),
            fausses_alertes=None,
            pluies_manquees=None,
            ex_aequo=bool(ex_aequo[i]),
        )
        for i, nom in enumerate(noms)
    ]
    scores.sort(key=lambda s: s.ecart_moyen)
    return Comparaison(
        scores=tuple(scores),
        nb_heures=len(observations),
        nb_jours=len(np.unique(jours)),
    )


def comparer_pluie(
    jours: np.ndarray,
    previsions: dict[str, np.ndarray],
    observations: np.ndarray,
    seuil: float = SEUIL_PLUIE_MM,
    nb_tirages: int = NB_TIRAGES,
) -> Comparaison:
    """Compare des Modèles sur la survenue de pluie.

    Les séries sont des hauteurs de précipitation en mm ; le seuil décide de ce qui
    compte comme pluie. Le Modèle est jugé sur son taux d'erreur global, mais les
    deux façons de se tromper sont rapportées séparément — elles n'ont pas le même
    coût pour l'utilisateur.
    """
    noms = list(previsions)
    reel = il_a_plu(observations, seuil)
    annonce = np.column_stack([il_a_plu(previsions[n], seuil) for n in noms])
    fautes = (annonce != reel[:, None]).astype(float)

    observees, tirees = _moyennes_reechantillonnees(jours, fautes, nb_tirages)
    i_meilleur = int(np.argmin(observees))
    ex_aequo = _ex_aequo_avec_meilleur(tirees, i_meilleur, NIVEAU_CONFIANCE)

    nb_annonces = annonce.sum(axis=0)
    nb_pluies = int(reel.sum())
    fausses = (annonce & ~reel[:, None]).sum(axis=0)
    manquees = (~annonce & reel[:, None]).sum(axis=0)

    scores = [
        ScoreModele(
            modele=nom,
            ecart_moyen=float(observees[i]),
            biais=None,
            fausses_alertes=float(fausses[i] / nb_annonces[i]) if nb_annonces[i] else None,
            pluies_manquees=float(manquees[i] / nb_pluies) if nb_pluies else None,
            ex_aequo=bool(ex_aequo[i]),
        )
        for i, nom in enumerate(noms)
    ]
    scores.sort(key=lambda s: s.ecart_moyen)
    return Comparaison(
        scores=tuple(scores),
        nb_heures=len(observations),
        nb_jours=len(np.unique(jours)),
    )
