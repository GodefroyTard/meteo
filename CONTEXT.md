# Fiabilité des modèles météo

Ce projet mesure, pour un lieu donné, quel modèle de prévision météo se trompe le moins,
en confrontant a posteriori ce que chaque modèle avait annoncé à ce qui a réellement été mesuré.

## Language

### Lieu

**Station**:
Un point de mesure physique qui produit des Observations. C'est la seule unité de lieu à laquelle
une fiabilité peut être rattachée — on ne juge jamais un point où personne ne mesure.
_Avoid_: Capteur, point de mesure, ville, commune

**Station de référence**:
La Station à laquelle un utilisateur est rattaché, choisie par distance et écart d'altitude.
Toujours affichée explicitement, avec sa distance et son dénivelé. Peut ne pas exister : aucune
Station suffisamment comparable n'est alors désignée.
_Avoid_: Station la plus proche, ma station

### Ce qui est annoncé

**Modèle**:
Un système de prévision numérique identifié (ECMWF, GFS, ICON-D2, AROME, ARPEGE). Deux résolutions
d'un même producteur sont deux Modèles distincts.
_Avoid_: Source, fournisseur, provider

**Prévision**:
Ce qu'un Modèle annonçait pour un instant donné, vu depuis une Anticipation donnée. Identifiée par
le triplet (Modèle, instant visé, Anticipation).
_Avoid_: Forecast, run, sortie de modèle

**Temps**:
Ce que le ciel fait à un instant donné — dégagé, couvert, brouillard, pluie, neige, orage.
Annoncé par un Modèle sous forme de code WMO, et regroupé en familles pour l'affichage. Tous
les Modèles n'en annoncent pas : AROME n'en publie aucun, et un Temps absent n'est jamais
déduit de la pluie prévue.
_Avoid_: Condition, météo, weather code, symbole

**Anticipation**:
Le nombre de jours entiers séparant le moment où une Prévision était affichée de l'instant qu'elle
vise. Varie de 1 à 7. Ce n'est pas un horizon en heures : l'écart réel entre l'émission du Modèle
et l'instant visé n'est pas connu.
_Avoid_: Horizon, échéance, lead time, délai

**Portée**:
L'Anticipation maximale au-delà de laquelle un Modèle ne prévoit plus rien. Elle va de 1 jour
(AROME, ICON-D2) à 7 jours (ECMWF, GFS). Deux Modèles ne sont comparables que sur les Anticipations
que tous deux couvrent.
_Avoid_: Range, échéance max, limite

### Ce qui s'est passé

**Observation**:
Une mesure réelle produite par une Station à un instant donné. Fait autorité : c'est la vérité
contre laquelle tout est jugé. Une réanalyse n'est jamais une Observation.
_Avoid_: Réel, mesure, ground truth, réalité

**Moyenne mesurée**:
Ce qu'une Station a relevé d'habitude autour d'une date : la moyenne de ses maximales et de
ses minimales sur une fenêtre de quinze jours centrée, les années précédentes, l'année en
cours exclue. Elle repose sur des Observations, jamais sur une réanalyse (ADR 0003), et
s'affiche toujours avec le nombre d'années sur lesquelles elle repose.
_Avoid_: Normale, normale de saison, normale climatique — celles-ci demandent trente ans

**Couverture**:
La proportion d'Observations valides effectivement disponibles sur une case de Verdict. En dessous
d'un minimum, la case n'est pas publiée : on refuse de conclure plutôt que de conclure sur peu.
_Avoid_: Complétude, taux de remplissage, disponibilité

### Le jugement

**Verdict**:
La réponse à « quel Modèle croire ici ». Toujours qualifié par une Station, une variable, une
Anticipation et une saison — un Verdict sans ces quatre qualificatifs n'a pas de sens.
_Avoid_: Classement, ranking, score, recommandation

**Écart**:
La différence entre une Prévision et l'Observation correspondante, pour une variable continue.
S'agrège en écart moyen — de combien un Modèle se trompe.
_Avoid_: Erreur, delta, résidu, MAE

**Biais**:
La tendance systématique d'un Modèle à sur- ou sous-estimer sur une Station donnée. Distinct de
l'Écart : un Modèle peut se tromper beaucoup sans Biais, ou peu mais toujours dans le même sens.
_Avoid_: Décalage, offset, erreur systématique

**Fausse alerte**:
Une Prévision annonçant de la pluie alors qu'il n'en est pas tombé.
_Avoid_: Faux positif

**Pluie manquée**:
De la pluie tombée qu'une Prévision n'annonçait pas.
_Avoid_: Faux négatif, oubli

**Ex aequo**:
L'état de plusieurs Modèles dont les Écarts ne sont pas distinguables compte tenu du volume de
mesures disponible. Un Verdict peut légitimement désigner plusieurs Modèles à égalité.
_Avoid_: Égalité, match nul, indécis
