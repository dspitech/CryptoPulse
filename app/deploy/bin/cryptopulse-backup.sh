#!/usr/bin/env bash
# Sauvegarde quotidienne : pg_dump envoye dans le Data Lake, snapshot hebdomadaire du disque de donnees.
# Les resultats sont publies pour Prometheus via le collecteur textfile de node-exporter.
set -uo pipefail
# shellcheck source=/dev/null
source /etc/cryptopulse/env.conf

ROOT=/opt/cryptopulse
BACKUP_DIR=/data/backups
STATE_DIR=/var/lib/cryptopulse
STATE_FILE=$STATE_DIR/backup.state
TEXTFILE_DIR=/var/lib/node_exporter/textfile
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
COMPOSE=(docker compose -p cryptopulse -f "$ROOT/app/deploy/docker-compose.yml" --env-file "$ROOT/runtime.env")
ARM="https://management.azure.com"
EXIT=0

log() { echo "[cryptopulse-backup] $*"; }

mkdir -p "$BACKUP_DIR" "$STATE_DIR" "$TEXTFILE_DIR"
touch "$STATE_FILE"

state_get() { grep "^$1=" "$STATE_FILE" | tail -n1 | cut -d= -f2- || true; }
state_set() {
  local tmp
  tmp=$(mktemp)
  grep -v "^$1=" "$STATE_FILE" > "$tmp" || true
  echo "$1=$2" >> "$tmp"
  mv "$tmp" "$STATE_FILE"
}

msi_token() {
  curl -fsS -H "Metadata:true" \
    "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=$1&client_id=${IDENTITY_CLIENT_ID}" \
    | jq -r .access_token
}

write_metrics() {
  local db_ts db_size snap_ts tmp
  db_ts=$(state_get db_ts)
  db_size=$(state_get db_size)
  snap_ts=$(state_get snap_ts)
  tmp=$(mktemp "$TEXTFILE_DIR/.cryptopulse_backup.XXXXXX")
  {
    if [ -n "$db_ts" ]; then
      echo "# HELP cryptopulse_backup_last_success_timestamp_seconds Unix time of the last successful database backup."
      echo "# TYPE cryptopulse_backup_last_success_timestamp_seconds gauge"
      echo "cryptopulse_backup_last_success_timestamp_seconds $db_ts"
      echo "# HELP cryptopulse_backup_size_bytes Size of the last successful database backup."
      echo "# TYPE cryptopulse_backup_size_bytes gauge"
      echo "cryptopulse_backup_size_bytes ${db_size:-0}"
    fi
    if [ -n "$snap_ts" ]; then
      echo "# HELP cryptopulse_disk_snapshot_last_success_timestamp_seconds Unix time of the last successful data disk snapshot."
      echo "# TYPE cryptopulse_disk_snapshot_last_success_timestamp_seconds gauge"
      echo "cryptopulse_disk_snapshot_last_success_timestamp_seconds $snap_ts"
    fi
  } > "$tmp"
  chmod 644 "$tmp"
  mv "$tmp" "$TEXTFILE_DIR/cryptopulse_backup.prom"
}

backup_database() {
  local file="$BACKUP_DIR/cryptopulse-$STAMP.dump" token blob
  log "pg_dump vers $file"
  if ! "${COMPOSE[@]}" exec -T postgres pg_dump -U cryptopulse -d cryptopulse -Fc --no-owner > "$file"; then
    log "pg_dump a echoue"
    rm -f "$file"
    return 1
  fi
  if ! "${COMPOSE[@]}" exec -T postgres pg_restore --list < "$file" > /dev/null; then
    log "l'archive produite est illisible"
    return 1
  fi
  token=$(msi_token "https%3A%2F%2Fstorage.azure.com%2F") || return 1
  blob="${BACKUP_PREFIX}$(date -u +%Y/%m/%d)/cryptopulse-$STAMP.dump"
  curl -fsS -X PUT \
    -H "Authorization: Bearer ${token}" -H "x-ms-version: 2022-11-02" \
    -H "x-ms-blob-type: BlockBlob" -H "Content-Type: application/octet-stream" \
    --data-binary @"$file" \
    "https://${STORAGE_ACCOUNT}.blob.core.windows.net/${BACKUP_CONTAINER}/${blob}" || return 1
  state_set db_ts "$(date +%s)"
  state_set db_size "$(stat -c %s "$file")"
  find "$BACKUP_DIR" -name 'cryptopulse-*.dump' -mtime +"${BACKUP_LOCAL_RETENTION_DAYS:-7}" -delete
  log "sauvegarde envoyee : ${BACKUP_CONTAINER}/${blob}"
}

snapshot_disk() {
  [ "${ENABLE_DISK_SNAPSHOTS:-false}" = "true" ] || return 0
  local last now token sub rg location name body list count excess old
  last=$(state_get snap_ts)
  now=$(date +%s)
  # Un snapshot par semaine suffit : les sauvegardes quotidiennes couvrent le reste.
  if [ -n "$last" ] && [ $((now - last)) -lt $((6 * 86400)) ]; then
    return 0
  fi
  token=$(msi_token "https%3A%2F%2Fmanagement.azure.com%2F") || return 1
  sub=$(echo "$DATA_DISK_ID" | cut -d/ -f3)
  rg=$(echo "$DATA_DISK_ID" | cut -d/ -f5)
  location=$(curl -fsS -H "Authorization: Bearer ${token}" "${ARM}${DATA_DISK_ID}?api-version=2023-04-02" | jq -r .location) || return 1
  name="snap-cryptopulse-data-$STAMP"
  body=$(jq -n --arg loc "$location" --arg src "$DATA_DISK_ID" \
    '{location: $loc, sku: {name: "Standard_LRS"}, tags: {cryptopulse: "data"},
      properties: {creationData: {createOption: "Copy", sourceResourceId: $src}, incremental: true}}')
  curl -fsS -X PUT -H "Authorization: Bearer ${token}" -H "Content-Type: application/json" -d "$body" \
    "${ARM}/subscriptions/${sub}/resourceGroups/${rg}/providers/Microsoft.Compute/snapshots/${name}?api-version=2023-04-02" \
    > /dev/null || return 1
  state_set snap_ts "$now"
  log "snapshot du disque demande : $name"

  # Retention : on conserve les N plus recents
  list=$(curl -fsS -H "Authorization: Bearer ${token}" \
    "${ARM}/subscriptions/${sub}/resourceGroups/${rg}/providers/Microsoft.Compute/snapshots?api-version=2023-04-02" \
    | jq -r '.value[] | select(.name | startswith("snap-cryptopulse-data-")) | .name' | sort) || return 0
  count=$(echo "$list" | grep -c . || true)
  excess=$((count - ${SNAPSHOT_RETENTION:-4}))
  if [ "$excess" -gt 0 ]; then
    echo "$list" | head -n "$excess" | while read -r old; do
      log "suppression du snapshot $old"
      curl -fsS -X DELETE -H "Authorization: Bearer ${token}" \
        "${ARM}/subscriptions/${sub}/resourceGroups/${rg}/providers/Microsoft.Compute/snapshots/${old}?api-version=2023-04-02" \
        > /dev/null || true
    done
  fi
}

backup_database || { log "ECHEC de la sauvegarde de la base"; EXIT=1; }
snapshot_disk || { log "ECHEC du snapshot du disque"; EXIT=1; }
write_metrics
exit "$EXIT"
