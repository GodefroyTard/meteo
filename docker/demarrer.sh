#!/bin/sh
# cron n'hérite pas de l'environnement du conteneur : on le dépose dans un fichier
# que chaque tâche recharge. Sans cela, METEO_DSN et le jeton Infoclimat seraient
# absents au moment où la tâche s'exécute, et le lot échouerait toutes les heures.
set -e
printenv | grep '^METEO_' | sed 's/^\([^=]*\)=\(.*\)$/export \1="\2"/' > /app/env.sh
chmod 600 /app/env.sh

echo "Lot planifié en place :"
crontab -l | grep -v '^#'
exec cron -f -L 2
