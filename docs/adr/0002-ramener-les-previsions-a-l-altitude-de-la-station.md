# Ramener les Prévisions à l'altitude de la Station

Autour de Grenoble, les Stations s'étagent de 220 m à 1965 m. Open-Meteo corrige déjà la
température sur un modèle numérique de terrain à 90 m, mais l'écart résiduel atteint 126 m sur les
crêtes (Moucherolle), soit 0,7 °C — l'ordre de grandeur même des différences entre Modèles que nous
cherchons à mesurer.

Nous passons donc `elevation=<altitude de la Station>` à chaque appel, pour que la Prévision et
l'Observation portent sur la même altitude. Sans cela, le classement refléterait le placement du
relief lissé de chaque Modèle plutôt que sa compétence de prévision — une information sans valeur
pour l'utilisateur.

## Conséquences

Nous mesurons la fiabilité du couple « Modèle + downscaling Open-Meteo », pas du Modèle brut. C'est
assumé : c'est cette chaîne-là que l'utilisateur consomme en pratique. Revenir sur ce choix
imposerait de re-télécharger l'intégralité des Prévisions backfillées.
