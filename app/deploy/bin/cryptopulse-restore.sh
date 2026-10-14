#!/usr/bin/env bash
# Restaure la base cryptopulse depuis une sauvegarde.
# Usage : sudo cryptopulse-restore [--yes] [latest | fichier.dump | chemin/du/blob/dans/gold]
set -euo pipefail
# shellcheck source=/dev/null
source /etc/cryptopulse/env.conf

ROOT=/opt/cryptopulse
COMPOSE=(docker compose -p cryptopulse -f "$ROOT/app/deploy/docker-compose.yml" --env-file "$ROOT/runtime.env")
ASSUME_YES=false
if [ "${1:-}" = "--yes" ]; then
  ASSUME_YES=true
  shift
fi
TARGET=${1:-latest}

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
DUMP="$WORKDIR/restore.dump"

msi_token() {
  curl -fsS -H "Metadata:true" \
    "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F&client_id=${IDENTITY_CLIENT_ID}" \
    | jq -r .access_token
}

if [ -f "$TARGET" ]; then
  cp "$TARGET" "$DUMP"
else
  TOKEN=$(msi_token)
  BASE="https://${STORAGE_ACCOUNT}.blob.core.windows.net/${BACKUP_CONTAINER}"
  if [ "$TARGET" = "latest" ]; then
    TARGET=$(curl -fsS -H "Authorization: Bearer ${TOKEN}" -H "x-ms-version: 2022-11-02" \
      "${BASE}?restype=container&comp=list&prefix=${BACKUP_PREFIX}" | python3 -c '
import sys
import xml.etree.ElementTree as ET
names = sorted(n.text for n in ET.parse(sys.stdin).getroot().iter("Name") if n.text and n.text.endswith(".dump"))
print(names[-1] if names else "")')
    [ -n "$TARGET" ] || { echo "Aucune sauvegarde trouvee dans ${BACKUP_CONTAINER}/${BACKUP_PREFIX}" >&2; exit 1; }
  fi
  echo "Telechargement de ${TARGET}"
  curl -fsS -H "Authorization: Bearer ${TOKEN}" -H "x-ms-version: 2022-11-02" "${BASE}/${TARGET}" -o "$DUMP"
fi

"${COMPOSE[@]}" exec -T postgres pg_restore --list < "$DUMP" > /dev/null \
  || { echo "Archive illisible : restauration annulee." >&2; exit 1; }

if [ "$ASSUME_YES" != "true" ]; then
  echo "ATTENTION : la base cryptopulse va etre remplacee par ${TARGET}."
  read -r -p "Taper 'oui' pour continuer : " answer
  [ "$answer" = "oui" ] || { echo "Annule."; exit 1; }
fi

echo "Arret des services qui utilisent la base"
"${COMPOSE[@]}" stop airflow-scheduler airflow-webserver dashboard api

echo "Restauration"
"${COMPOSE[@]}" exec -T postgres pg_restore -U cryptopulse -d cryptopulse \
  --clean --if-exists --no-owner --single-transaction < "$DUMP"

echo "Reapplication des droits des roles en lecture seule"
MON_PW=$(grep '^MONITORING_DB_PASSWORD=' "$ROOT/runtime.env" | cut -d= -f2-)
API_PW=$(grep '^API_DB_PASSWORD=' "$ROOT/runtime.env" | cut -d= -f2-)
"${COMPOSE[@]}" exec -T postgres psql -U cryptopulse -d cryptopulse -v ON_ERROR_STOP=1 \
  -v pw_monitoring="$MON_PW" -v pw_api="$API_PW" < "$ROOT/app/deploy/sql/roles.sql"

echo "Redemarrage des services"
"${COMPOSE[@]}" start airflow-scheduler airflow-webserver dashboard api
echo "Restauration terminee."
