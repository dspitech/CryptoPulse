#!/usr/bin/env bash
# Synchronise la VM avec l'artefact de deploiement publie par Terraform.
# Execute par cloud-init au premier boot, puis toutes les 5 minutes par un timer systemd.
set -euo pipefail
source /etc/cryptopulse/env.conf

exec 9>/var/lock/cryptopulse-sync.lock
flock -n 9 || exit 0

log() { echo "[cryptopulse-sync] $*"; }

# 1. Disque de donnees monte sur /data (cree au premier passage)
DISK=/dev/disk/azure/scsi1/lun0
if ! mountpoint -q /data; then
  for _ in $(seq 1 30); do [ -e "$DISK" ] && break; sleep 5; done
  [ -e "$DISK" ] || { log "disque de donnees introuvable"; exit 1; }
  blkid "$DISK" >/dev/null 2>&1 || mkfs.ext4 -L datadisk "$DISK"
  mkdir -p /data
  grep -q 'LABEL=datadisk' /etc/fstab || echo 'LABEL=datadisk /data ext4 defaults,nofail 0 2' >> /etc/fstab
  mount /data
  log "disque monte sur /data"
fi

# 2. Jeton Managed Identity pour le Storage
TOKEN=$(curl -fsS -H "Metadata:true" \
  "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F&client_id=${IDENTITY_CLIENT_ID}" \
  | jq -r .access_token)

URL="https://${STORAGE_ACCOUNT}.blob.core.windows.net/${ARTIFACT_CONTAINER}/${ARTIFACT_BLOB}"
AUTH=(-H "Authorization: Bearer ${TOKEN}" -H "x-ms-version: 2022-11-02")

STATE=/var/lib/cryptopulse
mkdir -p "$STATE" /opt/cryptopulse

# 3. Rien a faire si l'artefact n'a pas change
REMOTE_ETAG=$(curl -fsSI "${AUTH[@]}" "$URL" | tr -d '\r' | awk -F': ' 'tolower($1)=="etag"{print $2}')
LOCAL_ETAG=$(cat "$STATE/etag" 2>/dev/null || true)
if [ -n "$REMOTE_ETAG" ] && [ "$REMOTE_ETAG" = "$LOCAL_ETAG" ] && [ -f /opt/cryptopulse/app/deploy/deploy.sh ]; then
  exit 0
fi

# 4. Telechargement et deploiement
log "nouvel artefact detecte (${REMOTE_ETAG})"
curl -fsS "${AUTH[@]}" "$URL" -o /tmp/app.zip
rm -rf /opt/cryptopulse/app.new
mkdir -p /opt/cryptopulse/app.new
unzip -q -o /tmp/app.zip -d /opt/cryptopulse/app.new
# Mise a jour en place : conserve les inodes pour que les bind mounts Docker restent valides.
mkdir -p /opt/cryptopulse/app
rsync -a --delete --inplace /opt/cryptopulse/app.new/ /opt/cryptopulse/app/
rm -rf /opt/cryptopulse/app.new /tmp/app.zip

bash /opt/cryptopulse/app/deploy/deploy.sh

echo "$REMOTE_ETAG" > "$STATE/etag"
log "deploiement termine"
