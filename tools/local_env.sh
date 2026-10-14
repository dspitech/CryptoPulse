#!/usr/bin/env sh
# Genere app/deploy/.env.local avec des secrets aleatoires, une seule fois.
set -eu
ENV_FILE="$(dirname "$0")/../app/deploy/.env.local"
if [ -f "$ENV_FILE" ]; then
  echo "$ENV_FILE existe deja, il est conserve."
  exit 0
fi
rand() { openssl rand -hex "$1"; }
FERNET=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
umask 077
cat > "$ENV_FILE" <<ENV
POSTGRES_PASSWORD=$(rand 12)
AIRFLOW_ADMIN_PASSWORD=$(rand 8)
AIRFLOW_FERNET_KEY=${FERNET}
AIRFLOW_SECRET_KEY=$(rand 16)
GRAFANA_ADMIN_PASSWORD=$(rand 8)
API_KEY=$(rand 16)
MONITORING_DB_PASSWORD=$(rand 12)
API_DB_PASSWORD=$(rand 12)
NOTIFY_WEBHOOK_URL=
STORAGE_ACCOUNT=devstoreaccount1
AZURE_CLIENT_ID=
COINS=bitcoin,ethereum,solana
FRESHNESS_MAX_HOURS=3
PUBLIC_BIND=127.0.0.1
LOCAL_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://azurite:10000/devstoreaccount1;
ENV
echo "Fichier cree : $ENV_FILE"
