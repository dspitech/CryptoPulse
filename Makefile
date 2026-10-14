.RECIPEPREFIX = >
SHELL := /bin/bash

ENV ?= dev
INFRA := infra/envs/$(ENV)
TF := terraform -chdir=$(INFRA)
ALLOWED_IP ?= $(shell curl -fsS https://api.ipify.org 2>/dev/null)
PYTHON ?= python3
DBT_BIN ?= dbt
LOCAL_COMPOSE := docker compose -f app/deploy/docker-compose.yml -f app/deploy/docker-compose.local.yml --env-file app/deploy/.env.local

PROVIDERS := Microsoft.Compute Microsoft.Network Microsoft.Storage Microsoft.KeyVault \
  Microsoft.ManagedIdentity Microsoft.OperationalInsights Microsoft.Insights \
  Microsoft.DevTestLab Microsoft.Authorization Microsoft.Logic Microsoft.Consumption

.PHONY: help up providers bootstrap init check-ip plan deploy destroy output ssh-key secrets grafana-password \
  api-key tunnel dashboards fmt validate lint check test e2e setup-dev local-up local-down local-reset \
  local-logs local-trigger

help:
> @echo "Deploiement Azure (ENV=dev par defaut, ALLOWED_IP detectee automatiquement)"
> @echo "  make up                premier deploiement complet : providers + bootstrap + deploy"
> @echo "  make plan | deploy     terraform plan | apply"
> @echo "  make destroy           detruit l'environnement"
> @echo "  make output            URLs, IP et commandes utiles"
> @echo "  make ssh-key           recupere la cle SSH depuis Key Vault"
> @echo "  make secrets           mot de passe admin Airflow"
> @echo "  make grafana-password  mot de passe admin Grafana"
> @echo "  make api-key           cle de l'API de donnees"
> @echo "  make tunnel            tunnel SSH vers Prometheus (9090) et Alertmanager (9093)"
> @echo ""
> @echo "Developpement local (Docker, Azurite a la place du Data Lake)"
> @echo "  make local-up          demarre toute la plateforme en local"
> @echo "  make local-trigger     declenche le pipeline principal en local"
> @echo "  make local-logs        suit les logs"
> @echo "  make local-down        arrete (conserve les donnees) | make local-reset : supprime aussi les donnees"
> @echo ""
> @echo "Qualite"
> @echo "  make setup-dev         installe les dependances de test dans .venv et .venv-dbt"
> @echo "  make test              tests unitaires, dashboards, DAGs, API, cablage Terraform, lint"
> @echo "  make e2e               test d'integration (PostgreSQL, Azurite, dbt) dans des conteneurs jetables"
> @echo "  make dashboards        regenere les dashboards Grafana"
> @echo "  make fmt | validate    terraform fmt | terraform validate"

# ------------------------------------------------------------------ Azure
up: providers bootstrap deploy

providers:
> @for p in $(PROVIDERS); do az provider register --namespace $$p >/dev/null; echo "enregistre: $$p"; done

bootstrap:
> terraform -chdir=infra/bootstrap init -input=false
> terraform -chdir=infra/bootstrap apply -auto-approve -input=false

init:
> @terraform -chdir=infra/bootstrap output -raw backend_hcl > $(INFRA)/backend.hcl
> @echo 'key                  = "$(ENV).tfstate"' >> $(INFRA)/backend.hcl
> $(TF) init -input=false -reconfigure -backend-config=backend.hcl

check-ip:
> @test -n "$(ALLOWED_IP)" || { echo "ALLOWED_IP introuvable, utilisez: make deploy ALLOWED_IP=x.x.x.x"; exit 1; }

plan: init check-ip
> $(TF) plan -input=false -var 'allowed_ip=$(ALLOWED_IP)'

deploy: init check-ip
> $(TF) apply -auto-approve -input=false -var 'allowed_ip=$(ALLOWED_IP)'
> @$(TF) output

destroy: init check-ip
> $(TF) destroy -auto-approve -input=false -var 'allowed_ip=$(ALLOWED_IP)'

output:
> @$(TF) output

ssh-key:
> @mkdir -p ~/.ssh
> @az keyvault secret show --vault-name $$($(TF) output -raw key_vault_name) \
>   --name vm-ssh-private-key --query value -o tsv > ~/.ssh/cryptopulse-$(ENV)
> @chmod 600 ~/.ssh/cryptopulse-$(ENV)
> @echo "Cle ecrite dans ~/.ssh/cryptopulse-$(ENV)"

secrets:
> @az keyvault secret show --vault-name $$($(TF) output -raw key_vault_name) \
>   --name airflow-admin-password --query value -o tsv

grafana-password:
> @az keyvault secret show --vault-name $$($(TF) output -raw key_vault_name) \
>   --name grafana-admin-password --query value -o tsv

api-key:
> @az keyvault secret show --vault-name $$($(TF) output -raw key_vault_name) \
>   --name api-key --query value -o tsv

tunnel:
> ssh -i ~/.ssh/cryptopulse-$(ENV) -N -L 9090:localhost:9090 -L 9093:localhost:9093 \
>   cpadmin@$$($(TF) output -raw vm_public_ip)

# ------------------------------------------------------------------ local
local-up:
> sh tools/local_env.sh
> mkdir -p app/deploy/local/prometheus-targets
> $(LOCAL_COMPOSE) up -d --build
> @echo ""
> @echo "Plateforme locale demarree :"
> @echo "  Airflow    http://localhost:8080   (admin, mot de passe : grep AIRFLOW_ADMIN_PASSWORD app/deploy/.env.local)"
> @echo "  Grafana    http://localhost:3000   (admin, mot de passe : grep GRAFANA_ADMIN_PASSWORD app/deploy/.env.local)"
> @echo "  Streamlit  http://localhost:8501"
> @echo "  API        http://localhost:8000/docs (cle : grep API_KEY app/deploy/.env.local)"
> @echo "Premier chargement de donnees : make local-trigger"

local-trigger:
> $(LOCAL_COMPOSE) exec airflow-scheduler airflow dags trigger cryptopulse_pipeline
> @echo "Pour l'historique : $(LOCAL_COMPOSE) exec airflow-scheduler airflow dags trigger cryptopulse_backfill"

local-logs:
> $(LOCAL_COMPOSE) logs -f --tail=100

local-down:
> $(LOCAL_COMPOSE) down

local-reset:
> $(LOCAL_COMPOSE) down -v

# ------------------------------------------------------------------ qualite
setup-dev:
> $(PYTHON) -m venv .venv && .venv/bin/pip install -q -r requirements-dev.txt
> $(PYTHON) -m venv .venv-dbt && .venv-dbt/bin/pip install -q -r requirements-dbt.txt
> @echo "Environnements prets : utiliser PYTHON=.venv/bin/python DBT_BIN=.venv-dbt/bin/dbt"

lint:
> $(PYTHON) -m ruff check .

check:
> $(PYTHON) tools/check_terraform_wiring.py

test: lint check
> cd app/ingestion && $(PYTHON) -m pytest -q
> cd app/api && $(PYTHON) -m pytest -q
> cd app/airflow && $(PYTHON) -m pytest -q
> $(PYTHON) -m pytest -q tools

# Le test e2e supprime et recree les schemas de la base : il utilise donc des conteneurs jetables,
# jamais ceux de `make local-up`. Necessite Docker et les clients PostgreSQL (psql, pg_dump, pg_restore).
e2e:
> @docker rm -f cp-e2e-pg cp-e2e-azurite >/dev/null 2>&1 || true
> docker run -d --name cp-e2e-pg -e POSTGRES_USER=cryptopulse -e POSTGRES_PASSWORD=e2e -e POSTGRES_DB=cryptopulse \
>   -p 127.0.0.1:55432:5432 postgres:16 >/dev/null
> docker run -d --name cp-e2e-azurite -p 127.0.0.1:10100:10000 mcr.microsoft.com/azure-storage/azurite:3.33.0 \
>   azurite-blob --blobHost 0.0.0.0 --skipApiVersionCheck --loose >/dev/null
> @sleep 10
> @cd app/ingestion && CRYPTOPULSE_E2E=1 POSTGRES_HOST=127.0.0.1 POSTGRES_PORT=55432 POSTGRES_USER=cryptopulse \
>   POSTGRES_PASSWORD=e2e POSTGRES_DB=cryptopulse COINS=bitcoin,ethereum DBT_BIN=$(DBT_BIN) \
>   AZURE_STORAGE_CONNECTION_STRING="$$($(PYTHON) -c "from cryptopulse_ingestion.clients import AZURITE_CONNECTION_STRING as s; print(s.replace('10000', '10100'))")" \
>   $(PYTHON) -m pytest -m e2e tests/e2e -v; status=$$?; \
>   docker rm -f cp-e2e-pg cp-e2e-azurite >/dev/null 2>&1; exit $$status

dashboards:
> $(PYTHON) tools/generate_dashboards.py

fmt:
> terraform fmt -recursive infra

validate:
> @for d in infra/bootstrap infra/envs/dev infra/envs/prod; do \
>   terraform -chdir=$$d init -backend=false -input=false >/dev/null && terraform -chdir=$$d validate; \
> done
