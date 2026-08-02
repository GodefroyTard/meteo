# Scorer par anticipation en jours, pas par horizon en heures

L'API Previous Runs d'Open-Meteo expose les prévisions passées sous la forme « telle qu'elle
s'affichait il y a N jours » (`previous_dayN`, N de 1 à 7), et non sous la forme (run, échéance).
L'écart réel entre l'émission d'un run et l'instant visé n'est donc pas récupérable a posteriori.

Nous indexons la fiabilité sur l'Anticipation en jours entiers. C'est le seul axe que l'API rend
calculable rétroactivement, et c'est celui qui se formule naturellement pour un utilisateur
(« la veille, tel modèle avait raison »).

## Conséquences

Nous ne pourrons jamais produire de statistique par run (00Z vs 12Z) ni par horizon fin
(« AROME décroche après +30 h ») sans démarrer une collecte temps réel en parallèle. Ce serait un
nouvel axe de données, pas une migration de l'existant : les Prévisions déjà backfillées resteraient
valides et cohabiteraient avec les nouvelles.

Deux imprécisions découlent de ce choix, et il faut les avoir en tête pour lire un Verdict.

**Le délai réel flotte d'environ 24 heures à l'intérieur d'une Anticipation.** « Ce qui s'affichait
il y a 3 jours » recouvre des délais allant de 72 à 96 heures selon l'heure du run retenu et
l'heure visée. Les comparaisons restent valides — tous les Modèles subissent le même flou — mais
un écart moyen n'est pas rattachable à un horizon précis.

**Les Modèles ne tournent pas à la même fréquence, ce qui les avantage inégalement.** AROME et
ICON-D2 sortent 8 runs par jour, ARPEGE, ICON-EU et GFS 4, ECMWF 2. À Anticipation égale, un
Modèle à runs fréquents s'appuie sur un calcul plus récent : le classement récompense donc en
partie la cadence de rafraîchissement et pas seulement la qualité de prévision. L'effet existe
sans dominer — sur les hivers 2024-25 et 2025-26 à Saint-Martin-d'Hères, ICON-EU (4 runs/jour)
devance AROME (8 runs/jour) à J+1, 1,72 °C contre 2,10 °C.

Nous l'assumons pour la même raison que le downscaling d'altitude (ADR 0002) : nous mesurons ce que
l'utilisateur consulte réellement dans son application, pas la compétence d'un Modèle en
laboratoire. Un Modèle plus souvent réactualisé lui est effectivement plus utile.
