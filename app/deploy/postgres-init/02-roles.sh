#!/usr/bin/env bash
# Execute par l'image PostgreSQL au tout premier demarrage uniquement.
# deploy.sh rejoue le meme SQL a chaque deploiement pour couvrir les mises a jour.
set -euo pipefail
psql -v ON_ERROR_STOP=1 \
  -v pw_monitoring="$MONITORING_DB_PASSWORD" -v pw_api="$API_DB_PASSWORD" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /sql/roles.sql
