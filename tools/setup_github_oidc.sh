#!/usr/bin/env bash
# Prepare l'authentification OIDC entre GitHub Actions et Azure (aucun secret Azure dans GitHub).
# Usage : tools/setup_github_oidc.sh <organisation/depot> [environnement...]
# Necessite : az login avec le droit de creer une application Entra ID et des role assignments.
# Avec certains abonnements Azure for Students, la creation d'applications est interdite : voir README.
set -euo pipefail

REPO=${1:?Usage : $0 <organisation/depot> [environnement...]}
shift || true
ENVIRONMENTS=${*:-dev prod}
APP_NAME="sp-cryptopulse-github"

SUBSCRIPTION=$(az account show --query id -o tsv)
TENANT=$(az account show --query tenantId -o tsv)

echo "Creation de l'application ${APP_NAME}"
APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
az ad sp create --id "$APP_ID" > /dev/null
OBJECT_ID=$(az ad sp show --id "$APP_ID" --query id -o tsv)

add_credential() {
  local name=$1 subject=$2
  az ad app federated-credential create --id "$APP_ID" --parameters "{
    \"name\": \"${name}\",
    \"issuer\": \"https://token.actions.githubusercontent.com\",
    \"subject\": \"${subject}\",
    \"audiences\": [\"api://AzureADTokenExchange\"]
  }" > /dev/null
  echo "  identifiant federe : ${subject}"
}

add_credential "pull-request" "repo:${REPO}:pull_request"
for env in $ENVIRONMENTS; do
  add_credential "environment-${env}" "repo:${REPO}:environment:${env}"
done

# Terraform cree des role assignments : Contributor seul ne suffit pas.
for role in "Contributor" "User Access Administrator"; do
  az role assignment create --assignee-object-id "$OBJECT_ID" --assignee-principal-type ServicePrincipal \
    --role "$role" --scope "/subscriptions/${SUBSCRIPTION}" > /dev/null
  echo "  role attribue : ${role}"
done

# Acces au storage du state Terraform (backend authentifie par Entra ID)
if STATE_HCL=$(terraform -chdir=infra/bootstrap output -raw backend_hcl 2>/dev/null); then
  STATE_RG=$(echo "$STATE_HCL" | sed -n 's/^resource_group_name *= *"\(.*\)"/\1/p')
  STATE_SA=$(echo "$STATE_HCL" | sed -n 's/^storage_account_name *= *"\(.*\)"/\1/p')
  STATE_ID=$(az storage account show -g "$STATE_RG" -n "$STATE_SA" --query id -o tsv)
  az role assignment create --assignee-object-id "$OBJECT_ID" --assignee-principal-type ServicePrincipal \
    --role "Storage Blob Data Contributor" --scope "$STATE_ID" > /dev/null
  echo "  acces au state : ${STATE_SA}"
else
  echo "Bootstrap non execute : lancez make bootstrap puis relancez ce script."
  STATE_RG="" STATE_SA=""
fi

cat <<OUT

Variables a creer dans GitHub (Settings > Secrets and variables > Actions > Variables) :
  gh variable set AZURE_CLIENT_ID       --body "${APP_ID}"
  gh variable set AZURE_TENANT_ID       --body "${TENANT}"
  gh variable set AZURE_SUBSCRIPTION_ID --body "${SUBSCRIPTION}"
  gh variable set TF_STATE_RG           --body "${STATE_RG}"
  gh variable set TF_STATE_SA           --body "${STATE_SA}"
  gh variable set ALLOWED_IP            --body "<votre IP publique>"

Creez aussi les environnements GitHub dev et prod (avec validation manuelle pour prod).
OUT
