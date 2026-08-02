# Ne jamais utiliser une réanalyse comme Observation

Une réanalyse (ERA5, ERA5-Land) est tentante comme vérité terrain : couverture mondiale, historique
profond, une seule intégration. Nous l'interdisons comme source d'Observation.

Raison mesurée, pas théorique. Les mêmes Prévisions de la veille, jugées sur les mêmes
720 heures à Engins (905 m) en juin 2025, une fois contre la Station et une fois contre
ERA5-Land :

| Modèle  | contre la Station | contre ERA5 |
|---------|-------------------|-------------|
| ICON-EU | 1,08 °C — 1er     | 1,34 °C — 4e |
| AROME   | 1,10 °C — 2e      | 1,34 °C — 5e |
| ICON-D2 | 1,10 °C — 3e      | 1,17 °C — 2e |
| ARPEGE  | 1,33 °C — 4e      | 1,16 °C — 1er |
| ECMWF   | 1,83 °C — 5e      | 1,34 °C — 3e |
| GFS     | 2,46 °C — 6e      | 2,14 °C — 6e |

Le classement est bouleversé : AROME passe de 2e à 5e, ARPEGE de 4e à 1er. Et surtout,
ERA5 s'écarte de **1,44 °C** de la Station — davantage que la meilleure Prévision qu'il
prétend juger. La règle à en tirer tient en une phrase : une vérité plus fausse que ce
qu'elle mesure ne mesure rien.

L'explication n'est pas qu'ERA5 favoriserait son producteur — c'est ARPEGE, de Météo-France,
qui en sort premier. C'est que la réanalyse, à environ 9 km de maille, ne voit pas le relief
d'Engins. Les Modèles à maille grossière lui ressemblent parce qu'ils lissent le terrain de
la même façon ; ceux à maille fine sont pénalisés pour avoir capté des détails locaux réels
qu'ERA5 ignore. Juger sur une réanalyse revient donc à récompenser le lissage.

Les Observations viennent des Stations du réseau StatIC (Infoclimat), qui mesurent réellement,
au sol, à l'endroit dont on parle.

## Conséquences

Nous héritons des contraintes du réseau participatif : plafond de 7 jours consécutifs par requête,
clé API nominative, stations qui tombent en panne sans prévenir, et qualité de mesure inégale selon
la variable — un pluviomètre bouché ou sous-captant la neige en altitude reste utilisable pour la
température. La fiabilité d'une Station se déclare donc par variable, jamais en bloc.
