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

### La mémoire du lieu

**Poste**:
Un poste climatologique Météo-France, porteur d'une Série longue. Distinct de la Station : le Poste
raconte le passé du lieu, il ne départage jamais un Modèle. Ses mesures sont quotidiennes là où
celles d'une Station sont horaires, et les deux ne se mélangent pas (ADR 0008).
_Avoid_: Station Météo-France, station historique

**Série longue**:
La suite des Journées mesurées par un Poste, de sa première année à sa dernière. Sa valeur ne tient
pas à son étendue mais à ses **années pleines** : Grenoble-Saint-Geoirs court de 1950 à 2024 mais
n'a rien mesuré de 1952 à 1967.
_Avoid_: Historique, archive, historique climatique

**Tendance**:
La droite ajustée par moindres carrés sur les valeurs d'un jour de l'année, année après année.
Toujours accompagnée de son incertitude ; déclarée **significative** seulement quand l'intervalle
de confiance de sa pente exclut zéro. S'exprime par décennie, dans l'unité de ce qu'elle
ajuste : des °C pour une température, des jours pour un Franchissement.
_Avoid_: Évolution, courbe, régression, trend

**Cycle annuel**:
La courbe d'une année entière, du 1er janvier au 31 décembre, portant la moyenne
quotidienne lissée sur un mois. Superposés, les Cycles montrent la forme du climat d'un
lieu ; le lissage en retire les extrêmes, qui se lisent sur la Tendance et non ici.
_Avoid_: Saisonnalité, profil annuel, climatologie

**Franchissement**:
Le nombre de jours d'une année passant un seuil de température — sous 0 °C, au-dessus de
25 °C, au-dessus de 30 °C. Un comptage, pas une moyenne : c'est ce qui le rend robuste à
un changement d'instrument et immédiatement parlant. Ne se calcule que sur une année
suffisamment mesurée, jamais au prorata d'une année lacunaire.
_Avoid_: Jours chauds, dépassement, occurrence

**Saison sans gel**:
Ce qui sépare le dernier gel de printemps du premier gel d'automne, de part et d'autre du
1er juillet. Une année dont l'un des deux manque est omise : sa saison déborde de l'année
civile, et la borner inventerait une date.
_Avoid_: Période végétative, saison de croissance

**Record**:
La valeur extrême d'un jour du calendrier, et l'année qui la détient. Ne se lit qu'en
part de ce qu'un climat stable donnerait — proportionnelle aux années qu'une décennie
apporte — jamais en décompte brut, qui confondrait le signal avec la forme du calendrier.
_Avoid_: Extrême, maximum absolu, pic

**Prolongement**:
La même Tendance poursuivie au-delà des années mesurées. Ce n'est pas une prévision et ce n'est
pas un scénario climatique : c'est une droite prolongée, sous l'hypothèse — que rien ne garantit —
que le rythme passé se maintienne. Toujours tracé en tireté, jamais en trait plein.
_Avoid_: Projection, prévision, scénario, RCP

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
