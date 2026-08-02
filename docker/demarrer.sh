#!/bin/sh
# cron n'hérite pas de l'environnement du conteneur : on le dépose dans un fichier
# que chaque tâche recharge. Sans cela, METEO_DSN et le jeton Infoclimat seraient
# absents au moment où la tâche s'exécute, et le lot échouerait toutes les heures.
#
# PGPASSWORD ne porte pas le préfixe METEO_ mais doit suivre : c'est lui qui porte
# le mot de passe de la base, absent du DSN (voir docker-compose.yml).
set -e
printenv | grep -E '^(METEO_|PGPASSWORD=)' \
  | sed 's/^\([^=]*\)=\(.*\)$/export \1="\2"/' > /app/env.sh

# Le PATH aussi, et pour la même raison : cron donne à ses tâches un PATH minimal
# où /app/.venv/bin n'est pas, alors la tâche mourait sur « meteo: not found » —
# sans bruit ailleurs que dans les logs, l'app se contentant de ne plus fraîchir.
echo "export PATH=\"$PATH\"" >> /app/env.sh
chmod 600 /app/env.sh

echo "Lot planifié en place :"
crontab -l | grep -v '^#'
exec cron -f -L 2
