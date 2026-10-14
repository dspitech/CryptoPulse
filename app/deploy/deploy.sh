#!/usr/bin/env bash
# Execute sur la VM par cryptopulse-sync apres synchronisation de l'artefact.
# Recupere les secrets dans Key Vault via la Managed Identity, puis demarre la stack.
set -euo pipefail
# shellcheck source=/dev/null
source /etc/cryptopulse/env.conf

ROOT=/opt/cryptopulse
APP=$ROOT/app
ENABLE_HTTPS=${ENABLE_HTTPS:-false}
ENABLE_LOGGING=${ENABLE_LOGGING:-false}

# Profils Compose actives : https (Caddy) et logging (Loki, Promtail)
PROFILES=()
if [ "$ENABLE_HTTPS" = "true" ]; then PROFILES+=(https); fi
if [ "$ENABLE_LOGGING" = "true" ]; then PROFILES+=(logging); fi
COMPOSE_PROFILES=$(IFS=,; echo "${PROFILES[*]:-}")
export COMPOSE_PROFILES

COMPOSE=(docker compose -p cryptopulse -f "$APP/deploy/docker-compose.yml" --env-file "$ROOT/runtime.env")

KV_TOKEN=$(curl -fsS -H "Metadata:true" \
  "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fvault.azure.net&client_id=${IDENTITY_CLIENT_ID}" \
  | jq -r .access_token)

kv_secret() {
  curl -fsS -H "Authorization: Bearer ${KV_TOKEN}" \
    "https://${KEY_VAULT_NAME}.vault.azure.net/secrets/$1?api-version=7.4" | jq -r .value
}

# Secret facultatif : retourne une chaine vide s'il n'existe pas.
kv_secret_optional() {
  curl -sS -H "Authorization: Bearer ${KV_TOKEN}" \
    "https://${KEY_VAULT_NAME}.vault.azure.net/secrets/$1?api-version=7.4" | jq -r '.value // empty'
}

MONITORING_DB_PASSWORD=$(kv_secret monitoring-db-password)
API_DB_PASSWORD=$(kv_secret api-db-password)
NOTIFY_WEBHOOK_URL=$(kv_secret_optional notify-webhook-url)

# En HTTPS, les services ne sont joignables que par Caddy (ou par tunnel SSH sur 127.0.0.1)
if [ "$ENABLE_HTTPS" = "true" ]; then
  PUBLIC_BIND=127.0.0.1
  GRAFANA_ROOT_URL="https://${PUBLIC_FQDN}/"
  AIRFLOW_PROXY_FIX=True
else
  PUBLIC_BIND=0.0.0.0
  GRAFANA_ROOT_URL="http://localhost:3000/"
  AIRFLOW_PROXY_FIX=False
fi

(
  umask 077
  cat > "$ROOT/runtime.env" <<ENV
POSTGRES_PASSWORD=$(kv_secret postgres-password)
AIRFLOW_ADMIN_PASSWORD=$(kv_secret airflow-admin-password)
AIRFLOW_FERNET_KEY=$(kv_secret airflow-fernet-key)
AIRFLOW_SECRET_KEY=$(kv_secret airflow-secret-key)
GRAFANA_ADMIN_PASSWORD=$(kv_secret grafana-admin-password)
API_KEY=$(kv_secret api-key)
MONITORING_DB_PASSWORD=${MONITORING_DB_PASSWORD}
API_DB_PASSWORD=${API_DB_PASSWORD}
NOTIFY_WEBHOOK_URL=${NOTIFY_WEBHOOK_URL}
STORAGE_ACCOUNT=${STORAGE_ACCOUNT}
AZURE_CLIENT_ID=${IDENTITY_CLIENT_ID}
COINS=${COINS}
FRESHNESS_MAX_HOURS=${FRESHNESS_MAX_HOURS}
PUBLIC_BIND=${PUBLIC_BIND}
PUBLIC_FQDN=${PUBLIC_FQDN:-localhost}
ACME_EMAIL=${ACME_EMAIL:-admin@example.com}
GRAFANA_ROOT_URL=${GRAFANA_ROOT_URL}
AIRFLOW_PROXY_FIX=${AIRFLOW_PROXY_FIX}
COMPOSE_PROFILES=${COMPOSE_PROFILES}
ENV
)

# Repertoires de donnees et droits adaptes a chaque conteneur
install -d -m 0755 /data/postgres /data/caddy /data/promtail /data/backups
install -d -o 50000 -g 0 -m 0775 /data/airflow-logs
install -d -o 65534 -g 65534 -m 0755 /data/prometheus /data/alertmanager
install -d -o 472 -g 0 -m 0755 /data/grafana
install -d -o 10001 -g 10001 -m 0755 /data/loki
install -d -m 0755 /var/lib/node_exporter/textfile "$ROOT/prometheus-targets"
chown -R 50000:0 "$APP/airflow" "$APP/dbt" "$APP/ingestion"

# Commandes d'exploitation disponibles pour l'administrateur
for tool in backup restore; do
  printf '#!/bin/sh\nexec bash %s/deploy/bin/cryptopulse-%s.sh "$@"\n' "$APP" "$tool" > "/usr/local/sbin/cryptopulse-$tool"
  chmod 0750 "/usr/local/sbin/cryptopulse-$tool"
done

# Cibles Prometheus de la pile de logs : declarees uniquement si elle est activee
if [ "$ENABLE_LOGGING" = "true" ]; then
  cat > "$ROOT/prometheus-targets/logging.yml" <<'YAML'
- targets: ["loki:3100", "promtail:9080"]
YAML
else
  rm -f "$ROOT/prometheus-targets/logging.yml"
fi

# Configuration Alertmanager : webhook active uniquement si un secret existe
{
  cat <<'YAML'
route:
  receiver: default
  group_by: [alertname, severity]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
receivers:
  - name: default
YAML
  if [ -n "$NOTIFY_WEBHOOK_URL" ]; then
    printf '    webhook_configs:\n      - url: "%s"\n        send_resolved: true\n' "$NOTIFY_WEBHOOK_URL"
  fi
} > "$ROOT/alertmanager.yml"
chown root:65534 "$ROOT/alertmanager.yml"
chmod 0640 "$ROOT/alertmanager.yml"

# 1. PostgreSQL d'abord, pour creer les roles en lecture seule (monitoring_ro, api_ro)
"${COMPOSE[@]}" up -d postgres
for _ in $(seq 1 60); do
  "${COMPOSE[@]}" exec -T postgres pg_isready -U cryptopulse -d cryptopulse >/dev/null 2>&1 && break
  sleep 5
done

"${COMPOSE[@]}" exec -T postgres psql -U cryptopulse -d cryptopulse -v ON_ERROR_STOP=1 \
  -v pw_monitoring="$MONITORING_DB_PASSWORD" -v pw_api="$API_DB_PASSWORD" < "$APP/deploy/sql/roles.sql"

# 2. Le reste de la stack
"${COMPOSE[@]}" up -d --build --remove-orphans

# 3. Les services d'un profil desactive sont supprimes s'ils tournaient encore
DISABLED=()
if [ "$ENABLE_HTTPS" != "true" ]; then DISABLED+=(caddy); fi
if [ "$ENABLE_LOGGING" != "true" ]; then DISABLED+=(loki promtail); fi
if [ "${#DISABLED[@]}" -gt 0 ]; then
  docker compose -p cryptopulse -f "$APP/deploy/docker-compose.yml" --env-file "$ROOT/runtime.env" \
    --profile https --profile logging rm -sf "${DISABLED[@]}" >/dev/null 2>&1 || true
fi

# 4. Les composants qui lisent leur configuration au demarrage sont relances
RELOAD=(prometheus alertmanager postgres-exporter statsd-exporter blackbox-exporter)
if [ "$ENABLE_LOGGING" = "true" ]; then RELOAD+=(loki promtail); fi
if [ "$ENABLE_HTTPS" = "true" ]; then RELOAD+=(caddy); fi
"${COMPOSE[@]}" restart "${RELOAD[@]}" >/dev/null

docker image prune -f >/dev/null
