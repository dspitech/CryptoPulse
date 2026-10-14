# CryptoPulse

**Plateforme DataOps de bout en bout sur Azure, déployée à 100 % avec Terraform.**

![Terraform](https://img.shields.io/badge/Terraform-%E2%89%A5%201.5-7B42BC?logo=terraform&logoColor=white)
![Azure](https://img.shields.io/badge/Azure-VM%20%7C%20ADLS%20Gen2%20%7C%20Key%20Vault-0078D4?logo=microsoftazure&logoColor=white)
![Airflow](https://img.shields.io/badge/Airflow-4%20DAGs-017CEE?logo=apacheairflow&logoColor=white)
![dbt](https://img.shields.io/badge/dbt-1.8.8-FF694B?logo=dbt&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-5%20dashboards-F46800?logo=grafana&logoColor=white)
![Licence](https://img.shields.io/badge/licence-MIT-green)

CryptoPulse ingère chaque heure des prix de cryptomonnaies, les actualités du secteur et l'indice Fear and Greed. Elle stocke tout dans un Data Lake, transforme les données avec dbt, détecte les anomalies, produit des prévisions, contrôle la qualité, expose les résultats par une API et cinq dashboards Grafana, et se sauvegarde seule.

Le projet prolonge les TP 1 à 8 du cours DataOps (Azurite, SQLite, dbt, Airflow, Terraform, rapports qualité) et supprime toutes leurs étapes manuelles : un seul `make up` déploie la plateforme, et un simple `make deploy` la met à jour.

| | |
|---|---|
| **Déploiement** | Une commande, aucune connexion SSH requise, 10 à 15 minutes jusqu'à la plateforme complète |
| **Coût** | De l'ordre de 50 USD par mois en continu (VM, disques, IP), moins avec l'extinction nocturne (voir [Coûts](#15-coûts-et-planification-de-la-vm)) |
| **Accès** | HTTPS automatique, limité à votre IP. SSH par clé générée et stockée dans Key Vault |
| **Reprise** | Sauvegarde PostgreSQL quotidienne, snapshots du disque, reconstruction par Terraform |

Auteur : Pape Lo. Cours DataOps, année 2025 - 2026.

## Sommaire

1. [Fonctionnalités](#1-fonctionnalités)
2. [Architecture](#2-architecture)
3. [Données et traitements](#3-données-et-traitements)
4. [Structure du dépôt](#4-structure-du-dépôt)
5. [Prérequis](#5-prérequis)
6. [Démarrage rapide](#6-démarrage-rapide)
7. [Configuration Terraform](#7-configuration-terraform)
8. [Déploiement automatique](#8-déploiement-automatique)
9. [Déploiement pas à pas](#9-déploiement-pas-à-pas)
10. [Accès SSH à la VM](#10-accès-ssh-à-la-vm)
11. [Accès aux services](#11-accès-aux-services)
12. [API de données](#12-api-de-données)
13. [Dashboards, métriques et alertes](#13-dashboards-métriques-et-alertes)
14. [Sauvegardes et restauration](#14-sauvegardes-et-restauration)
15. [Coûts et planification de la VM](#15-coûts-et-planification-de-la-vm)
16. [Sécurité](#16-sécurité)
17. [Développement local](#17-développement-local)
18. [Tests et qualité](#18-tests-et-qualité)
19. [CI/CD](#19-cicd)
20. [Dépannage](#20-dépannage)
21. [Limites et évolutions](#21-limites-et-évolutions)
22. [Documentation complémentaire](#22-documentation-complémentaire)
23. [Captures d'écran](#23-captures-décran)
24. [Licence et auteur](#24-licence-et-auteur)

## 1. Fonctionnalités

| Domaine | Fonctionnalité |
|---|---|
| Ingestion | Prix horaires CoinGecko, historique (backfill jusqu'à 90 jours en points horaires), actualités par flux RSS, Fear and Greed Index |
| Data Lake | Zones `bronze` (JSON brut), `silver` (Parquet nettoyé), `gold` (marts en Parquet, rapports qualité, sauvegardes), partitions `year=/month=/day=` |
| Transformation | dbt : 12 modèles (staging, marts, sentiment, prévisions), tests de données, OHLC journalier, moyennes mobiles 7 et 30 jours, volatilité |
| Analytique | Détection d'anomalies par z-score, prévisions à 7 jours (ARIMA) avec mesure de leur précision passée, sentiment des actualités |
| Qualité | Validation du JSON, tests dbt, rapport qualité historisé, contrôle de fraîcheur, DAG qui échoue si un contrôle est en FAIL |
| Restitution | 5 dashboards Grafana provisionnés, dashboard Streamlit, API REST en lecture seule |
| Observabilité | Prometheus, Alertmanager, 5 exporters, Loki et Promtail (logs), 22 règles d'alerte, alertes Azure Monitor |
| Fiabilité | Sauvegarde PostgreSQL quotidienne vers le Data Lake, snapshots hebdomadaires du disque, script de restauration, rétention automatique |
| Sécurité | Secrets dans Key Vault, identités managées, HTTPS automatique, rôles PostgreSQL en lecture seule, Private Endpoints optionnels, scans en CI |
| Exploitation | Démarrage et extinction automatiques de la VM, alerte de budget, déploiement par artefact, redéploiement sans recréer la VM |
| Développement | Environnement local complet avec Azurite, test d'intégration de bout en bout, pre-commit, Dependabot |
| CI/CD | Validation, tests, scans de sécurité, estimation des coûts (Infracost), déploiement GitHub Actions par OIDC |

## 2. Architecture

```
Poste local ou Cloud Shell                       GitHub Actions (optionnel, OIDC)
        |  make up                                        |
        +--------------------- terraform apply -----------+
                                    |
                                    v
+--------------------------------------------------------------------------------+
| Azure (norwayeast), un resource group par environnement                        |
|                                                                                |
|  Key Vault ------ secrets generes, cle SSH            Azure Monitor + Log      |
|  Identite managee -- RBAC vers Key Vault et Storage    Analytics (alertes)     |
|  Data Lake ADLS Gen2 : bronze, silver, gold, artifacts                         |
|  Logic App : demarrage quotidien de la VM                                      |
|  Private Endpoints (optionnel) : Key Vault et Storage                          |
|                                                                                |
|  VNet + NSG (IP autorisee uniquement, sauf le port 80 pour Let's Encrypt)      |
|    +-- VM Ubuntu 24.04 Standard_B2s + disque de donnees (snapshots)            |
|          cloud-init -> timer systemd -> docker compose                         |
|          +-- Caddy (HTTPS)      443 Grafana, 8443 Airflow, 9443 Streamlit,     |
|          |                      8444 API                                       |
|          +-- PostgreSQL 16, Airflow (webserver, scheduler), API, Streamlit     |
|          +-- Prometheus, Alertmanager, Grafana, Loki, Promtail                 |
|          +-- node-exporter, cAdvisor, postgres, statsd, blackbox exporters     |
+--------------------------------------------------------------------------------+
```

Les diagrammes détaillés (infrastructure, services, flux de données, séquence de déploiement, planning) sont dans [docs/architecture.md](docs/architecture.md). Les décisions et leurs alternatives sont dans les [ADR](docs/adr/README.md).

Kubernetes (AKS) n'est pas utilisé : il n'est pas disponible sur l'abonnement Azure for Students. La VM `Standard_B2s` héberge donc tous les services avec Docker Compose, et cloud-init automatise l'ensemble (voir l'[ADR 0001](docs/adr/0001-vm-docker-compose-plutot-qu-aks.md)).

## 3. Données et traitements

### Les quatre DAGs Airflow

| DAG | Déclenchement | Chaîne de tâches |
|---|---|---|
| `cryptopulse_pipeline` | Chaque heure, minute 00 | `ingest_prices`, `validate_bronze`, `load_staging`, `dbt_build`, `export_lake`, `quality_report`, `check_quality`, `freshness_check`, `notify` |
| `cryptopulse_sentiment` | Chaque heure, minute 20 | `ingest_news`, `ingest_fear_greed`, `dbt_build_sentiment` |
| `cryptopulse_forecast` | Chaque jour à 02h30 UTC | `run_forecast`, `dbt_build_forecast` |
| `cryptopulse_backfill` | Manuel, paramètre `days` de 2 à 365 (90 par défaut) | `backfill_history`, `dbt_build` |

Principes appliqués :

- **Idempotence** : un blob par heure et par source, clé primaire `(coin_id, snapshot_ts)` et `ON CONFLICT DO NOTHING`. Relancer une tâche ne crée aucun doublon, et un backfill n'écrase jamais un snapshot réel.
- **Exécutions dbt sérialisées** : les quatre DAGs partagent un pool Airflow `dbt` à un seul slot, car dbt recrée des tables que d'autres DAGs peuvent lire.
- **Échecs visibles** : en cas d'échec, un webhook est appelé si `notify_webhook_url` est fournie.

### Couches du warehouse PostgreSQL

| Schéma | Contenu |
|---|---|
| `raw` | `prices`, `news_sentiment`, `fear_greed` : données chargées depuis le Data Lake, sans transformation |
| `staging` | `stg_prices` (prix nettoyés), `stg_news` |
| `marts` | `dim_coins`, `fct_latest_prices`, `fct_daily_prices`, `fct_price_indicators`, `fct_price_anomalies`, `dim_data_freshness`, `fct_daily_sentiment`, `fct_fear_greed`, `fct_forecasts_latest`, `fct_forecast_accuracy` |
| `ops` | `quality_runs` (historique des contrôles), `forecast_history` (historique des prévisions) |

### Data Lake

| Zone | Contenu | Chemin |
|---|---|---|
| `bronze` | Réponses brutes des sources | `coingecko/markets/year=/month=/day=/`, `coingecko/market_chart/...`, `news/rss/...`, `fear_greed/...` |
| `silver` | Prix nettoyés en Parquet, un fichier par jour | `prices/year=/month=/day=/prices.parquet` |
| `gold` | Marts en Parquet, rapports qualité, sauvegardes | `marts/<table>/snapshot=AAAA-MM-JJ/`, `reports/quality/`, `backups/` |
| `artifacts` | Code de l'application publié par Terraform | `app.zip` |

### Méthodes analytiques

- **Anomalies** : le rendement entre deux snapshots est comparé à la moyenne et à l'écart-type des 7 derniers jours. Au-delà d'un z-score de 3 (variable dbt `anomaly_z_threshold`), avec au moins 24 observations, le point est signalé. Un rendement n'est calculé que si les deux snapshots sont distants de 3 heures au plus, pour ne pas confondre une interruption de la VM avec une anomalie de marché.
- **Prévisions** : ARIMA(1,1,1) sur le logarithme des clôtures journalières complètes (21 jours minimum), horizon de 7 jours, intervalle à 80 %. Une marche aléatoire prend le relais si l'ajustement échoue. Le modèle `fct_forecast_accuracy` compare les prévisions passées aux clôtures réelles. **Ces prévisions sont une illustration statistique et non un conseil financier.**
- **Sentiment** : score VADER sur le titre et le résumé des articles de CoinDesk, Cointelegraph et Decrypt (flux configurables). Seuls le titre, le lien, la source et le score sont conservés. VADER est un lexique anglais : le score est approximatif.

## 4. Structure du dépôt

```
cryptopulse/
├── infra/
│   ├── bootstrap/               Storage du state Terraform (une seule fois)
│   ├── modules/
│   │   ├── platform/            Module racine qui assemble tous les autres
│   │   ├── network/             VNet, NSG, sous-réseau des Private Endpoints
│   │   ├── storage/             Data Lake, cycle de vie, publication de l'artefact
│   │   ├── keyvault/            Key Vault, RBAC, génération des secrets
│   │   ├── compute/             VM, disque, cloud-init, IP publique avec DNS
│   │   ├── monitoring/          Log Analytics, alertes Azure Monitor
│   │   ├── private_endpoints/   Key Vault et Storage en réseau privé
│   │   ├── autostart/           Logic App de démarrage quotidien
│   │   └── budget/              Budget mensuel et alertes de coût
│   └── envs/{dev,prod}/         Environnements (appellent uniquement platform)
├── app/                         Code déployé sur la VM (empaqueté par Terraform)
│   ├── deploy/                  docker-compose.yml, deploy.sh, bin/ (sauvegarde, restauration), sql/
│   ├── airflow/                 Dockerfile et 4 DAGs
│   ├── ingestion/               Package Python, tests unitaires et e2e
│   ├── dbt/                     Projet dbt
│   ├── api/                     API FastAPI
│   ├── dashboard/               Application Streamlit
│   ├── caddy/                   Caddyfile (HTTPS)
│   └── monitoring/              Prometheus, règles, exporters, Loki, Promtail, Grafana
├── tools/                       Générateur de dashboards, vérificateur Terraform, scripts, tests
├── docs/                        Architecture, runbook, ADR
├── .github/                     Workflows CI/CD, Dependabot
├── Makefile
└── README.md
```

## 5. Prérequis

### Compte et droits Azure

- Un abonnement Azure (Azure for Students convient).
- Le rôle **Owner** sur l'abonnement, ou à défaut **Contributor** et **User Access Administrator** : Terraform crée des attributions de rôles (identité managée de la VM vers Key Vault et Storage).
- Une **vraie** adresse e-mail pour `alert_email` : elle reçoit les alertes Azure Monitor et les alertes de budget, et sert de contact à Let's Encrypt. **Une adresse en `@example.com` (valeur d'exemple `you@example.com`) est refusée par Let's Encrypt : Caddy n'obtient alors aucun certificat et le navigateur affiche `ERR_CONNECTION_RESET`.**

### Outils

| Outil | Version | Utilité | Installation |
|---|---|---|---|
| Azure CLI (`az`) | récente | Connexion, resource providers, lecture des secrets Key Vault | [Installer Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) |
| Terraform | 1.5.0 ou plus | Déploie toute l'infrastructure | [Installer Terraform](https://developer.hashicorp.com/terraform/install) |
| GNU `make` et `bash` | toute version | Le Makefile s'exécute avec `/bin/bash` | Fournis par Linux et macOS |
| `curl` | toute version | Détection de votre IP publique | Fourni par défaut |
| Client OpenSSH (`ssh`, `scp`) | toute version | Connexion à la VM (facultatif pour déployer) | Fourni par Linux, macOS et Windows 10 ou plus |
| Docker | récente | Uniquement pour le [développement local](#17-développement-local) et `make e2e` | [Installer Docker](https://docs.docker.com/get-docker/) |

### Où lancer les commandes

| | Poste local (Linux, macOS, WSL 2) | Azure Cloud Shell (bash) |
|---|---|---|
| Outils | À installer | Fournis (az, Terraform, make, curl) |
| Authentification | `az login` | Déjà connecté |
| `ALLOWED_IP` | Détectée automatiquement | **À indiquer explicitement** : la détection renverrait l'IP du Cloud Shell, pas celle de votre navigateur |
| SSH vers la VM | Direct | Ne fonctionne que si `allowed_ip` est l'IP sortante du Cloud Shell, qui change d'une session à l'autre : préférez votre poste |

Sous Windows, utilisez WSL 2 (Ubuntu) ou le Cloud Shell : le Makefile suppose un shell bash.

## 6. Démarrage rapide

Cinq commandes, depuis un poste local (voir la [section 9](#9-déploiement-pas-à-pas) pour le détail de chaque étape).

```bash
# 1. Récupérer le code
git clone https://github.com/dspitech/CryptoPulse.git
cd CryptoPulse

# 2. OBLIGATOIRE : remplacer alert_email par votre vraie adresse (pas @example.com)
nano infra/envs/dev/terraform.tfvars      # alert_email = "votre.vraie@adresse.com"

# 3. Se connecter à Azure (inutile dans le Cloud Shell)
az login

# 4. Déployer : providers Azure, state Terraform, infrastructure et application
make up ALLOWED_IP=203.0.113.10     # remplacer par l'IP publique de VOTRE poste

# 5. Après 10 à 15 minutes, récupérer les accès
make output                          # URLs, IP, nom du Key Vault
make grafana-password                # mot de passe de Grafana (utilisateur admin)
make ssh-key                         # écrit la clé SSH dans ~/.ssh/cryptopulse-dev
```

Si vous avez lancé `make up` avec l'adresse d'exemple, corrigez `alert_email` puis relancez `make deploy ALLOWED_IP=<IP de votre PC>` : la VM est recréée (le disque de données est conservé) et le certificat est alors émis.

Pour connaître votre IP publique, depuis votre poste (pas depuis le Cloud Shell) : `curl -s https://api.ipify.org`.

Ouvrez ensuite l'URL `grafana_url` affichée par `make output`, puis suivez les [premiers pas](#premiers-pas-après-le-déploiement). Pour vous connecter à la VM en SSH, voir la [section 10](#10-accès-ssh-à-la-vm).

## 7. Configuration Terraform

Les valeurs se règlent dans `infra/envs/dev/terraform.tfvars` et `infra/envs/prod/terraform.tfvars`. Le seul réglage à modifier avant un premier déploiement est `alert_email`.

| Variable | Défaut | Rôle |
|---|---|---|
| `project` | `cryptopulse` | Préfixe des ressources |
| `environment` | selon l'environnement | `dev` ou `prod` |
| `location` | `norwayeast` | Région Azure |
| `allowed_ip` | fournie par le Makefile | Seule IP autorisée sur SSH, Grafana, Airflow, le dashboard et l'API |
| `alert_email` | à renseigner | Destinataire des alertes Azure Monitor, des alertes de budget et contact Let's Encrypt |
| `vm_size` | `Standard_B2s` | Taille de la VM |
| `admin_username` | `cpadmin` | Utilisateur administrateur de la VM |
| `coins` | 5 cryptos en dev, 7 en prod | Identifiants CoinGecko suivis |
| `enable_ssh` | `true` en dev, `false` en prod | Ouvre le port 22 depuis `allowed_ip` (voir [Accès SSH](#10-accès-ssh-à-la-vm)) |
| `data_disk_gb` | 32 en dev, 64 en prod | Taille du disque de données |
| `auto_shutdown_time` | `2100` en dev | Extinction quotidienne au format HHMM, vide pour désactiver |
| `auto_shutdown_timezone` | `UTC` | Fuseau de l'extinction et du démarrage |
| `auto_start_time` | `0700` en dev | Démarrage quotidien par la Logic App, vide pour désactiver |
| `enable_https` | `true` | HTTPS automatique avec Caddy et Let's Encrypt |
| `enable_logging` | `true` | Loki et Promtail (environ 400 Mo de RAM) |
| `enable_disk_snapshots` | `true` | Snapshot hebdomadaire incrémental du disque de données |
| `snapshot_retention` | `4` | Nombre de snapshots conservés |
| `backup_retention_days` | 30 en dev, 90 en prod | Rétention des sauvegardes PostgreSQL dans le Data Lake |
| `enable_private_endpoints` | `false` en dev, `true` en prod | Key Vault et Storage joignables en réseau privé (environ 7 USD par mois et par endpoint) |
| `lock_public_access` | `false` | Interdit l'accès public au Key Vault et au Storage |
| `deployer_ip` | vide | IP fixe du poste qui exécute Terraform, obligatoire avec `lock_public_access` |
| `monthly_budget` | `0` | Budget mensuel du resource group, 0 pour désactiver |
| `notify_webhook_url` | vide | Webhook d'alerte, fourni par `TF_VAR_notify_webhook_url` et jamais écrit dans un fichier |
| `app_source_dir` | automatique | Dossier `app/` publié comme artefact |
| `tags` | vide | Étiquettes supplémentaires sur toutes les ressources |

Deux garde-fous Terraform empêchent les configurations dangereuses : `lock_public_access` exige `enable_private_endpoints` (sinon la VM perdrait l'accès au Key Vault) et `deployer_ip` (sinon Terraform ne pourrait plus écrire dans le Key Vault).

## 8. Déploiement automatique

Un seul `terraform apply` suffit. Aucune connexion SSH n'est nécessaire pour déployer ou mettre à jour.

```mermaid
flowchart LR
    A["make up"] --> B["terraform apply"]
    B --> C["Key Vault : secrets et clé SSH"]
    B --> D["Data Lake : app.zip"]
    B --> E["VM + cloud-init"]
    E --> F["cryptopulse-sync"]
    D --> F
    F --> G["deploy.sh"]
    C --> G
    G --> H["docker compose up"]
    H --> I["Plateforme en service"]
```

Voici ce qui se passe, dans l'ordre.

1. Terraform génère une clé SSH, tous les mots de passe, la clé d'API et la clé Fernet, et les écrit dans Key Vault.
2. Terraform empaquette `app/` en `app.zip` (sans secrets locaux ni tests) et le dépose dans le container `artifacts`.
3. Terraform crée la VM, avec une étiquette DNS publique, et un cloud-init minimal : Docker (avec rotation des logs), swap de 4 Go, script de synchronisation, minuteries systemd.
4. Au premier démarrage, `cryptopulse-sync` monte le disque de données sur `/data`, télécharge `app.zip` avec l'identité managée, puis lance `deploy.sh`.
5. `deploy.sh` lit les secrets dans Key Vault, écrit `runtime.env` (permissions 600), démarre PostgreSQL, crée les rôles en lecture seule, puis exécute `docker compose up -d --build` pour le reste. Caddy obtient les certificats Let's Encrypt.
6. Toutes les 5 minutes, la synchronisation compare l'ETag de l'artefact : si le code a changé, les fichiers sont mis à jour en place (`rsync --inplace`, qui garde valides les bind mounts Docker) et la stack est redéployée. Cela couvre aussi un premier essai interrompu par la propagation des droits RBAC.
7. Chaque nuit, une minuterie lance la sauvegarde.

Le premier démarrage complet prend 10 à 15 minutes après la fin de `terraform apply` (paquets, build des images, certificats).

## 9. Déploiement pas à pas

### Étape 1 : récupérer le code

```bash
git clone https://github.com/dspitech/CryptoPulse.git
cd CryptoPulse
```

### Étape 2 : configurer l'environnement

Éditez `infra/envs/dev/terraform.tfvars`. Le seul réglage obligatoire est `alert_email`. Les autres valeurs par défaut conviennent à un premier déploiement (liste complète à la [section 7](#7-configuration-terraform)).

```bash
nano infra/envs/dev/terraform.tfvars      # alert_email = "votre.vraie@adresse.com"
```

**Attention :** n'utilisez jamais une adresse `@example.com`. Let's Encrypt la refuse (`contact email has forbidden domain "example.com"`), Caddy ne peut pas émettre le certificat HTTPS et le site reste inaccessible. Si cela vous arrive, corrigez le fichier puis lancez `make deploy ALLOWED_IP=<IP de votre PC>`.

| Réglage | Pourquoi y toucher |
|---|---|
| `alert_email` | Obligatoire : vraie adresse, destinataire des alertes et contact Let's Encrypt (jamais `@example.com`) |
| `monthly_budget` | Mettre par exemple `40` pour être alerté avant d'épuiser le crédit |
| `auto_shutdown_time`, `auto_start_time` | Horaires d'extinction et de démarrage de la VM (UTC par défaut) |
| `coins` | Cryptomonnaies suivies |

Pour recevoir les alertes sur un webhook (facultatif) :

```bash
export TF_VAR_notify_webhook_url="https://exemple.com/webhook"
```

### Étape 3 : se connecter à Azure

```bash
az login                                   # inutile dans le Cloud Shell
az account show --query name -o tsv        # vérifier l'abonnement actif
az account set --subscription "<nom ou id>"   # si plusieurs abonnements
```

### Étape 4 : lancer le déploiement

```bash
make up ALLOWED_IP=203.0.113.10
```

`make up` enchaîne trois cibles que vous pouvez aussi lancer une à une :

| Cible | Rôle |
|---|---|
| `make providers` | Enregistre les resource providers Azure nécessaires (dont Logic et Consumption). À faire une fois par abonnement |
| `make bootstrap` | Crée le storage qui conserve le state Terraform (resource group `rg-cryptopulse-tfstate`) |
| `make deploy` | Initialise Terraform et applique l'infrastructure de l'environnement choisi |

`ALLOWED_IP` est la seule adresse autorisée sur SSH, Grafana, Airflow, le dashboard et l'API. Sans ce paramètre, l'IP est détectée avec `api.ipify.org`, ce qui est faux dans le Cloud Shell : indiquez-la explicitement.

Terraform se termine en quelques minutes et affiche les sorties (`grafana_url`, `airflow_url`, `dashboard_url`, `api_url`, `fqdn`, `ssh_command`...). **La VM continue ensuite à s'installer pendant 10 à 15 minutes** (paquets, build des images, certificats).

### Étape 5 : attendre la fin de l'installation

Les services répondent d'abord par une erreur de connexion, puis par un avertissement de certificat, puis normalement. Pour suivre l'avancement depuis la VM (voir la [section 10](#10-accès-ssh-à-la-vm)) :

```bash
cloud-init status --wait                              # fin de l'initialisation
sudo journalctl -u cryptopulse-sync -f                # déploiement en cours
docker compose -p cryptopulse ps                      # état des conteneurs
```

Sans SSH, testez simplement l'API (aucune clé requise pour ce point d'accès) :

```bash
curl -s https://<fqdn>:8444/health
```

### Étape 6 : récupérer les URLs et les identifiants

```bash
make output                # toutes les URLs, l'IP de la VM, le nom du Key Vault
make grafana-password      # Grafana : utilisateur admin
make secrets               # Airflow : utilisateur admin
make api-key               # clé de l'API, à envoyer dans l'en-tête X-API-Key
```

Les secrets ont été générés par Terraform et se trouvent uniquement dans Key Vault. Ils ne sont jamais écrits dans Git.

### Premiers pas après le déploiement

1. Ouvrir **Airflow** (`airflow_url`, utilisateur `admin`) : les quatre DAGs sont actifs, le pipeline principal tourne chaque heure.
2. Déclencher dans cet ordre `cryptopulse_backfill`, puis `cryptopulse_pipeline`, puis `cryptopulse_forecast` (bouton ▶ de la ligne du DAG, puis **Trigger DAG w/ config** pour le backfill, paramètre `days` à 90 par défaut). Le forecast est ignoré tant qu'il n'a pas 21 jours d'historique, et un premier passage du pipeline sur une base vide peut échouer sur `check_quality` : relancez-le après le backfill : l'historique alimente moyennes mobiles, volatilité, anomalies et prévisions. Autre méthode, depuis la VM : `cp-compose exec airflow-scheduler airflow dags trigger cryptopulse_backfill --conf '{"days": 90}'` (l'alias `cp-compose` est défini dans le [runbook](docs/runbook.md#3-opérations-courantes)).
3. Ouvrir **Grafana** (`grafana_url`, utilisateur `admin`) : le dashboard Marché est la page d'accueil.
4. Tester l'**API** sur `api_docs_url` avec la clé obtenue par `make api-key`.

### Référence des commandes

| Commande | Effet |
|---|---|
| `make help` | Liste toutes les cibles |
| `make up` | Premier déploiement complet |
| `make plan` | Prévisualise les changements sans les appliquer |
| `make deploy` | Applique l'infrastructure et publie le nouveau code |
| `make output` | Affiche URLs, IP et nom du Key Vault |
| `make ssh-key` | Écrit la clé SSH dans `~/.ssh/cryptopulse-<ENV>` |
| `make tunnel` | Tunnel SSH vers Prometheus et Alertmanager |
| `make secrets`, `make grafana-password`, `make api-key` | Lisent les secrets dans Key Vault |
| `make destroy` | Détruit l'environnement |

Ajoutez `ENV=prod` à n'importe quelle commande pour viser la production (`make deploy ENV=prod`).

### Mettre à jour

Modifier le code de `app/` ou l'infrastructure, puis `make deploy`. Un changement de code est déployé dans les 5 minutes sans recréer la VM. Modifier `coins` ou une option qui change le cloud-init recrée la VM (le disque de données est conservé).

Si votre IP publique change, relancez `make deploy ALLOWED_IP=<nouvelle IP>` : seul le NSG est modifié.

### Détruire

```bash
make destroy              # environnement dev
make destroy ENV=prod
```

Supprimez ensuite le resource group `rg-cryptopulse-tfstate` si vous voulez retirer aussi le state. Le Key Vault est purgé à la destruction, ce qui permet de redéployer sans conflit de nom.

## 10. Accès SSH à la VM

### Comment ça marche

Vous n'avez jamais à créer ni à envoyer de clé SSH : Terraform s'en charge.

1. Terraform génère une paire de clés RSA 4096 bits.
2. La **clé publique** est installée sur la VM pour l'utilisateur `cpadmin` (variable `admin_username`).
3. La **clé privée** est stockée dans le Key Vault, dans le secret `vm-ssh-private-key`.
4. Le groupe de sécurité réseau (NSG) n'autorise le port 22 que depuis `allowed_ip`, et seulement si `enable_ssh = true` (cas de `dev`, pas de `prod`).

Il suffit donc de **télécharger la clé privée depuis Key Vault**, de la protéger, puis de se connecter.

### Ce qu'il faut avant de commencer

| Condition | Comment la vérifier |
|---|---|
| Le déploiement est terminé | `make output` affiche `vm_public_ip` et `key_vault_name` |
| La VM est démarrée | En `dev`, elle s'éteint à 21h00 UTC et redémarre à 07h00 UTC |
| Votre IP est autorisée | Elle doit être égale à `allowed_ip` (sinon `make deploy ALLOWED_IP=<votre IP>`) |
| SSH est activé | `enable_ssh = true` (valeur par défaut en `dev`) |
| Vous avez accès au Key Vault | Même compte Azure que celui qui a déployé (rôle Key Vault Administrator), ou au minimum Key Vault Secrets User |

### Étape 1 : télécharger la clé privée

**Méthode A : avec `make` (Linux, macOS, WSL, Cloud Shell)**

```bash
make ssh-key                # écrit ~/.ssh/cryptopulse-dev avec les bonnes permissions
make ssh-key ENV=prod       # écrit ~/.ssh/cryptopulse-prod
```

La commande crée `~/.ssh` si besoin, lit le secret `vm-ssh-private-key` et applique `chmod 600`.

**Méthode B : avec Azure CLI seule (depuis n'importe quel poste, sans cloner le dépôt)**

Récupérez d'abord le nom du Key Vault (`make output`, ligne `key_vault_name`, de la forme `kv-cryptopulse-dev-xxxx`), puis :

```bash
# Linux, macOS, WSL
mkdir -p ~/.ssh
az keyvault secret show --vault-name <key_vault_name> \
  --name vm-ssh-private-key --query value -o tsv > ~/.ssh/cryptopulse-dev
chmod 600 ~/.ssh/cryptopulse-dev
```

```powershell
# Windows PowerShell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
az keyvault secret show --vault-name <key_vault_name> `
  --name vm-ssh-private-key --query value -o tsv |
  Set-Content -Encoding ascii "$env:USERPROFILE\.ssh\cryptopulse-dev"
icacls "$env:USERPROFILE\.ssh\cryptopulse-dev" /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

Sous Windows PowerShell 5.1, n'utilisez pas l'opérateur `>` : il écrit en UTF-16 et la clé devient illisible pour `ssh`.

**Méthode D : depuis le Cloud Shell, puis téléchargement sur votre PC**

Utile si vous avez déployé depuis le Cloud Shell et voulez vous connecter depuis votre poste. Dans le Cloud Shell :

```bash
make ssh-key                    # écrit ~/.ssh/cryptopulse-dev
download ~/.ssh/cryptopulse-dev # télécharge le fichier vers votre PC
```

Si la commande `download` n'est pas disponible, utilisez le bouton **Gérer les fichiers**, puis **Télécharger** de la barre du Cloud Shell, et saisissez le chemin `~/.ssh/cryptopulse-dev`.

Sur votre PC, placez ensuite le fichier dans `~/.ssh/` (`%USERPROFILE%\.ssh\` sous Windows) et protégez-le :

```bash
chmod 600 ~/.ssh/cryptopulse-dev          # Linux, macOS, WSL
```

```powershell
icacls "$env:USERPROFILE\.ssh\cryptopulse-dev" /inheritance:r /grant:r "$($env:USERNAME):(R)"
```

Supprimez ensuite la copie du Cloud Shell (`rm ~/.ssh/cryptopulse-dev`) si vous ne vous y connectez pas en SSH : la clé donne un accès administrateur à la VM.

**Méthode C : depuis le portail Azure**

1. Portail Azure, ouvrir le Key Vault `kv-cryptopulse-dev-xxxx`.
2. **Objets**, puis **Secrets**, puis `vm-ssh-private-key`.
3. Ouvrir la version courante et cliquer sur **Afficher la valeur du secret**.
4. Copier tout le contenu, de `-----BEGIN OPENSSH PRIVATE KEY-----` à `-----END OPENSSH PRIVATE KEY-----` inclus, dans un fichier `~/.ssh/cryptopulse-dev`, avec un retour à la ligne final.
5. Appliquer les permissions (`chmod 600` sous Linux et macOS, `icacls` sous Windows comme ci-dessus).

Si le portail ou la CLI répond `Forbidden`, votre compte n'a pas de rôle sur le Key Vault ou votre IP n'est pas autorisée (cas de `lock_public_access = true`, où seule `deployer_ip` passe).

### Étape 2 : se connecter

```bash
make output                                   # repérer ssh_command et vm_public_ip
ssh -i ~/.ssh/cryptopulse-dev cpadmin@<IP_VM>
```

Le nom DNS (`fqdn`) fonctionne aussi à la place de l'IP. L'IP publique est statique : elle ne change pas à l'arrêt de la VM. À la première connexion, `ssh` demande de confirmer l'empreinte du serveur : répondez `yes`.

Pour ne plus retaper la commande, ajoutez ce bloc à `~/.ssh/config` :

```text
Host cryptopulse-dev
    HostName <IP_VM ou fqdn>
    User cpadmin
    IdentityFile ~/.ssh/cryptopulse-dev
    IdentitiesOnly yes
```

Ensuite, `ssh cryptopulse-dev` suffit. Ce même nom d'hôte est utilisable avec `scp` et avec l'extension Remote - SSH de VS Code.

### Étape 3 : explorer la VM

```bash
cloud-init status --wait                              # fin du premier démarrage
sudo journalctl -u cryptopulse-sync -n 50 --no-pager  # dernier déploiement
systemctl list-timers 'cryptopulse-*'                 # synchronisation et sauvegarde
docker compose -p cryptopulse ps                      # état des conteneurs
free -h && df -h / /data                              # mémoire et disques
```

L'application est dans `/opt/cryptopulse` et les données dans `/data`. Les opérations courantes (logs, redémarrage, shell SQL, déclenchement de DAG) sont dans le [runbook](docs/runbook.md#3-opérations-courantes).

### Accéder à Prometheus et Alertmanager

Ces services ne sont jamais exposés sur Internet. Ouvrez un tunnel SSH :

```bash
make tunnel
```

Tant que la commande tourne, Prometheus est sur `http://localhost:9090` et Alertmanager sur `http://localhost:9093`. Arrêtez le tunnel avec `Ctrl+C`. La cible suppose l'utilisateur `cpadmin` et la clé `~/.ssh/cryptopulse-dev` : adaptez la commande si vous avez changé `admin_username`.

### Copier des fichiers

```bash
scp -i ~/.ssh/cryptopulse-dev cpadmin@<IP_VM>:/data/backups/cryptopulse-<horodatage>.dump .
```

### En production (`enable_ssh = false`)

Le port 22 est fermé. Deux possibilités :

- **Commande d'exécution Azure**, sans ouvrir de port :

  ```bash
  az vm run-command invoke -g rg-cryptopulse-prod -n vm-cryptopulse-prod \
    --command-id RunShellScript --scripts "docker compose -p cryptopulse ps"
  ```

- **Réactivation temporaire** : passer `enable_ssh = true` dans `infra/envs/prod/terraform.tfvars`, lancer `make deploy ENV=prod ALLOWED_IP=<votre IP>`, intervenir, puis remettre `false` et redéployer.

### Dépannage SSH

| Symptôme | Cause probable | Action |
|---|---|---|
| `Connection timed out` | Votre IP a changé, ou la VM est éteinte, ou `enable_ssh = false` | `make deploy ALLOWED_IP=<votre IP>` (seul le NSG change). Vérifier l'état de la VM dans le portail |
| `Connection refused` | La VM démarre encore | Attendre quelques minutes et réessayer |
| `WARNING: UNPROTECTED PRIVATE KEY FILE` | Permissions trop larges | `chmod 600 ~/.ssh/cryptopulse-dev` (`icacls` sous Windows) |
| `Permission denied (publickey)` | Mauvais utilisateur, mauvaise clé, ou clé remplacée par un nouveau déploiement | Utiliser `cpadmin`, relancer `make ssh-key` pour récupérer la clé courante |
| `Load key ... invalid format` | Clé tronquée, encodage UTF-16 ou ligne finale manquante | Retélécharger la clé avec la méthode A ou B |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | La VM a été recréée | `ssh-keygen -R <IP_VM>` puis se reconnecter |
| `Forbidden` ou `Caller is not authorized` sur Key Vault | Rôle manquant ou IP non autorisée sur le coffre | Utiliser le compte qui a déployé, ou vérifier `deployer_ip` si `lock_public_access = true` |

### Bonnes pratiques

- La clé privée donne un accès administrateur (`sudo`) à la VM : ne la committez jamais (le `.gitignore` exclut `*.pem` mais pas un fichier nommé autrement) et ne la partagez pas.
- Supprimez-la des postes partagés ou temporaires, y compris du Cloud Shell, après usage.
- Le state Terraform contient aussi cette clé : ne le partagez pas non plus.
- Pour changer de clé : `terraform apply -replace='module.platform.tls_private_key.vm'` **recrée la VM** (le disque de données est conservé). Relancez ensuite `make ssh-key` et `ssh-keygen -R <IP_VM>`. Voir la [rotation des secrets](docs/runbook.md#5-rotation-des-secrets).

## 11. Accès aux services

### Adresses et identifiants

| Service | URL en HTTPS (défaut) | URL en HTTP (`enable_https = false`) | Utilisateur | Mot de passe ou clé |
|---|---|---|---|---|
| Grafana | `https://<fqdn>` | `http://<IP>:3000` | `admin` | `make grafana-password` |
| Airflow | `https://<fqdn>:8443` | `http://<IP>:8080` | `admin` | `make secrets` |
| Dashboard Streamlit | `https://<fqdn>:9443` | `http://<IP>:8501` | aucun | aucun, limité par IP |
| API | `https://<fqdn>:8444/docs` | `http://<IP>:8000/docs` | aucun | clé `make api-key` en en-tête `X-API-Key` |
| Prometheus et Alertmanager | `localhost:9090` et `:9093` par tunnel SSH (`make tunnel`) | idem | aucun | aucun |
| VM (SSH) | `cpadmin@<IP>` sur le port 22 | idem | `cpadmin` | clé du Key Vault ([section 10](#10-accès-ssh-à-la-vm)) |

`make output` affiche les URLs exactes. Le nom `<fqdn>` a la forme `cryptopulse-dev-xxxx.norwayeast.cloudapp.azure.com`. Prometheus, Alertmanager, PostgreSQL et Loki ne sont jamais exposés publiquement.

### Où sont les secrets

| Secret | Nom dans Key Vault | Commande |
|---|---|---|
| Mot de passe Grafana | `grafana-admin-password` | `make grafana-password` |
| Mot de passe Airflow | `airflow-admin-password` | `make secrets` |
| Clé de l'API | `api-key` | `make api-key` |
| Clé SSH privée | `vm-ssh-private-key` | `make ssh-key` |
| Mot de passe PostgreSQL et autres | `postgres-password`, `monitoring-db-password`, `api-db-password`... | `az keyvault secret show --vault-name <key_vault_name> --name <nom> --query value -o tsv` |

### Si une page ne s'ouvre pas

0. `ERR_CONNECTION_RESET` ou erreur de certificat : sur la VM, `docker compose -p cryptopulse logs caddy --tail=30`. Si vous lisez `forbidden domain "example.com"`, `alert_email` est resté à sa valeur d'exemple : corrigez-le dans `infra/envs/dev/terraform.tfvars` et relancez `make deploy ALLOWED_IP=<IP de votre PC>`.
1. Vérifiez que votre IP actuelle est bien `allowed_ip` : tout le reste est bloqué par le NSG.
2. Vérifiez que la VM est démarrée (extinction à 21h00 UTC en `dev`).
3. Un certificat invalide pendant les premières minutes est normal : Caddy attend l'émission Let's Encrypt.
4. Consultez le [dépannage](#20-dépannage).

## 12. API de données

L'API est en lecture seule, protégée par une clé dans l'en-tête `X-API-Key`. Elle lit uniquement les schémas `marts` et `ops`, jamais les données brutes. La documentation interactive est sur `/docs`.

| Endpoint | Contenu |
|---|---|
| `GET /health` | État de l'API et de la base (sans clé) |
| `GET /v1/coins` | Cryptos suivies |
| `GET /v1/prices/latest` | Dernier prix de chaque crypto |
| `GET /v1/prices/{coin_id}/latest` | Dernier prix d'une crypto |
| `GET /v1/prices/{coin_id}/daily` | OHLC journalier, paramètres `start`, `end`, `limit` |
| `GET /v1/indicators/{coin_id}` | Moyennes mobiles, variation, volatilité |
| `GET /v1/anomalies` | Anomalies détectées, paramètres `coin_id`, `hours`, `limit` |
| `GET /v1/forecasts/{coin_id}` | Prévision à 7 jours avec intervalle à 80 % |
| `GET /v1/sentiment/{coin_id}` | Sentiment quotidien des actualités |
| `GET /v1/fear-greed` | Fear and Greed Index |
| `GET /v1/quality/latest` | Derniers contrôles qualité |

```bash
API="https://<fqdn>:8444"
KEY=$(make api-key)

curl -s -H "X-API-Key: $KEY" "$API/v1/prices/latest"
curl -s -H "X-API-Key: $KEY" "$API/v1/prices/bitcoin/daily?limit=30"
curl -s -H "X-API-Key: $KEY" "$API/v1/anomalies?hours=168"
curl -s -H "X-API-Key: $KEY" "$API/v1/forecasts/ethereum"
```

Les nombres sont renvoyés en nombres JSON. Une base encore vide renvoie 503 avec un message explicite. L'API expose ses propres métriques à Prometheus (requêtes par route et statut, latence) sur un port interne.

## 13. Dashboards, métriques et alertes

### Dashboards Grafana

Cinq dashboards sont créés dans le dossier `CryptoPulse`. Le dashboard Marché est la page d'accueil.

| Dashboard | Sources | Contenu |
|---|---|---|
| CryptoPulse : Marché | PostgreSQL | Prix, variation 24 h, capitalisation, volume. Bougies japonaises OHLC, répartition de la capitalisation, performance comparée en base 100, cours avec moyennes mobiles, volatilité, variation journalière. Prévision à 7 jours avec intervalle, table des anomalies, annotations rouges des anomalies sur les courbes, cotations en temps réel. Variables Crypto et Comparaison |
| CryptoPulse : Pipeline et qualité | Prometheus, PostgreSQL | Fraîcheur, contrôles en échec, volumes, tâches Airflow par état, durées, executor, disponibilité des services, historique des contrôles, alertes actives. Sauvegardes (âge, taille, snapshot du disque) et API (requêtes, latence p95, erreurs 5xx) |
| CryptoPulse : Infrastructure | Prometheus | CPU, mémoire, swap, disques, charge, réseau de la VM. CPU, mémoire, trafic et ancienneté par conteneur. PostgreSQL : état, taille, connexions, cache hit ratio, verrous, transactions |
| CryptoPulse : Sentiment | PostgreSQL | Fear and Greed (jauge, classification, historique), sentiment moyen par crypto, volume d'articles, prix et sentiment, titres récents avec lien et score |
| CryptoPulse : Logs | Loki | Volume de logs et erreurs par service, logs des conteneurs avec recherche. Nécessite `enable_logging = true` |

Les dashboards sont générés par `tools/generate_dashboards.py` puis versionnés en JSON. Pour en modifier un : éditer le générateur, `make dashboards`, `make test`, `make deploy`. Grafana recharge sous une minute.

### Métriques métier

postgres-exporter exécute les requêtes de `app/monitoring/postgres-exporter/queries.yaml` :

| Métrique | Signification |
|---|---|
| `cryptopulse_freshness_age_hours` | Âge du dernier snapshot de prix |
| `cryptopulse_rows_total`, `cryptopulse_rows_last_24h` | Volumétrie de `raw.prices` |
| `cryptopulse_quality_failed_checks`, `cryptopulse_quality_warning_checks` | Contrôles qualité des 3 dernières heures |
| `cryptopulse_price_usd`, `cryptopulse_price_pct_24h` | Dernier prix et variation 24 h par crypto |
| `cryptopulse_anomalies_last_24h` | Anomalies détectées par crypto sur 24 h |
| `cryptopulse_fear_greed_value` | Dernier Fear and Greed Index |
| `cryptopulse_backup_last_success_timestamp_seconds`, `cryptopulse_backup_size_bytes`, `cryptopulse_disk_snapshot_last_success_timestamp_seconds` | État des sauvegardes (collecteur textfile de node-exporter) |

Airflow envoie ses métriques en StatsD, converties par statsd-exporter (`airflow_task_finished_total`, `airflow_dagrun_duration_seconds`, `airflow_scheduler_heartbeat_total`, `airflow_executor_*`). Seules les métriques listées dans `statsd-mapping.yml` sont conservées.

### Règles d'alerte

Les règles sont dans `app/monitoring/prometheus/rules/`.

| Alerte | Condition | Sévérité |
|---|---|---|
| TargetDown | Cible non collectée pendant 5 min (hors pile de logs) | critical |
| HighCpuUsage | CPU supérieure à 85 % pendant 15 min | warning |
| LowMemory | Moins de 8 % de mémoire disponible pendant 10 min | warning |
| DataDiskAlmostFull, RootDiskAlmostFull | Disque occupé à plus de 85 % | warning |
| ServiceProbeFailing | Sonde HTTP en échec pendant 5 min | critical |
| PostgresDown | PostgreSQL inaccessible pendant 2 min | critical |
| PostgresConnectionsHigh | Plus de 80 % des connexions utilisées | warning |
| AirflowSchedulerHeartbeatMissing | Aucun heartbeat du scheduler pendant 5 min | critical |
| AirflowTaskFailures | Au moins une tâche en échec sur 1 h | warning |
| AirflowDagImportErrors | Erreur d'import de DAG | warning |
| DataStale | Dernier snapshot de plus de 3 h pendant 30 min | critical |
| DataMetricsAbsent | Aucune métrique de fraîcheur pendant 2 h | warning |
| QualityChecksFailing | Contrôle qualité en FAIL | critical |
| PriceAnomalyDetected | Anomalie de prix sur 24 h | info |
| LargePriceMove | Variation de prix supérieure à 15 % sur 24 h | info |
| DatabaseBackupMissing | Dernière sauvegarde de plus de 36 h | critical |
| DatabaseBackupMetricAbsent | Aucune sauvegarde réussie depuis 2 jours | warning |
| DiskSnapshotTooOld | Dernier snapshot de plus de 10 jours | warning |
| ApiServerErrors | Plus de 5 erreurs 5xx en 15 min | warning |
| ApiHighLatency | Latence p95 supérieure à 2 s pendant 10 min | warning |
| LoggingStackDown | Loki ou Promtail indisponible | warning |

Les alertes en cours s'affichent dans le dashboard Pipeline et qualité. Pour les recevoir à l'extérieur, fournissez `TF_VAR_notify_webhook_url` avant `make deploy` : le même webhook sert à Alertmanager et aux échecs de DAG. Alertmanager envoie son JSON natif, donc le webhook doit accepter du JSON arbitraire (Power Automate, Logic App, n8n, relais Teams ou Slack). Sans webhook, les alertes restent visibles dans Grafana et Prometheus. Les alertes email d'Azure Monitor (CPU, disponibilité de la VM) fonctionnent indépendamment.

La procédure à suivre pour chaque alerte est dans le [runbook](docs/runbook.md#7-playbooks-par-alerte).

## 14. Sauvegardes et restauration

| Quoi | Fréquence | Où | Conservation |
|---|---|---|---|
| Base `cryptopulse` (`pg_dump` format custom, vérifié par `pg_restore --list`) | Chaque nuit à 03h30 UTC | `gold/backups/AAAA/MM/JJ/` et `/data/backups` | Data Lake : 30 jours en dev, 90 en prod (règle de cycle de vie). VM : 7 jours |
| Disque de données (snapshot incrémental) | Chaque semaine | Snapshots du resource group | 4 derniers |
| Données brutes | À chaque ingestion | `bronze` | Illimitée, tier Cool après 30 jours |

Le Storage conserve aussi 7 jours de suppression logique des blobs et des containers. Les sauvegardes sont envoyées avec l'identité managée, et leur âge, leur taille et celui du dernier snapshot sont exposés à Prometheus.

Sur la VM :

```bash
sudo cryptopulse-backup                    # sauvegarde immédiate
sudo cryptopulse-restore latest            # restaure la dernière sauvegarde du Data Lake
sudo cryptopulse-restore /data/backups/cryptopulse-20261009T033000Z.dump
```

La restauration vérifie l'archive, arrête Airflow, l'API et le dashboard, restaure en une transaction, réapplique les droits des rôles en lecture seule et redémarre les services. La procédure complète, y compris la restauration d'un snapshot du disque et un test trimestriel, est dans le [runbook](docs/runbook.md#4-sauvegardes-et-restauration). Le RPO est de 24 heures au pire pour la base.

## 15. Coûts et planification de la VM

Ordre de grandeur mensuel pour `norwayeast`, à confirmer avec le calculateur de prix Azure :

| Ressource | Estimation |
|---|---|
| VM `Standard_B2s` en continu | 35 à 40 USD |
| Disques (64 Go système, 32 Go données) | environ 8 USD |
| IP publique Standard | environ 4 USD |
| Snapshots, Storage, Log Analytics, Key Vault | quelques USD |
| Logic App de démarrage | moins de 1 USD |
| Private Endpoints (optionnel) | environ 7 USD chacun |
| Prometheus, Grafana, Loki et exporters | aucun coût supplémentaire (conteneurs sur la VM) |

L'abonnement Students offre environ 100 USD de crédit. Le dev s'éteint à 21h00 UTC et redémarre à 07h00 UTC par une Logic App, ce qui fait tourner la VM environ 14 heures par jour. Les minuteries de sauvegarde et de synchronisation sont configurées pour rattraper un passage manqué pendant que la VM est éteinte. L'alerte de disponibilité de la VM est désactivée quand l'extinction automatique est active, pour éviter une alerte chaque nuit.

Pour être prévenu avant d'épuiser le crédit, activez le budget : `monthly_budget = 40` dans `terraform.tfvars`. Les alertes partent à 50 %, 80 % et 100 % du dépensé, et à 100 % de la prévision, vers `alert_email`. Selon le type d'offre, l'API de budgets peut ne pas être disponible sur un abonnement Students : en cas d'erreur, remettez `monthly_budget = 0` et relancez le déploiement. Sur chaque pull request, la CI peut aussi estimer le coût avec Infracost.

La plateforme complète occupe la mémoire des 4 Go de la VM avec des limites par conteneur, des réglages Airflow réduits, une rétention Prometheus bornée et un swap de 4 Go. Si `LowMemory` se déclenche souvent, désactivez Loki (`enable_logging = false`) ou passez à `Standard_B2ms` (8 Go).

## 16. Sécurité

| Sujet | Mise en oeuvre |
|---|---|
| Secrets | Générés par Terraform, stockés dans Key Vault, jamais saisis par un humain ni écrits dans Git. `runtime.env` est en permissions 600 |
| Authentification Azure | Identité managée pour la VM, aucune clé de stockage utilisée par l'application. Droits limités : lecture et écriture du Data Lake, lecture des secrets, création de snapshots de son disque |
| Accès SSH | Paire de clés RSA 4096 générée par Terraform, clé privée dans Key Vault (`vm-ssh-private-key`), port 22 limité à `allowed_ip/32` et fermé en production (`enable_ssh = false`). Voir la [section 10](#10-accès-ssh-à-la-vm) |
| Réseau | NSG : tous les ports applicatifs et SSH limités à `allowed_ip/32`. Seul le port 80 est ouvert à Internet, pour le défi Let's Encrypt, et Caddy n'y répond qu'avec le défi ou une redirection. PostgreSQL, Prometheus, Alertmanager et Loki ne sont pas exposés |
| HTTPS | Certificats Let's Encrypt automatiques par Caddy, HSTS, en-têtes de sécurité, TLS 1.2 minimum sur le Storage |
| PostgreSQL | Rôles `monitoring_ro` et `api_ro` en lecture seule. `api_ro` ne lit que `marts` et `ops`, avec un délai de requête de 10 s et 10 connexions au plus. Le script de rôles est rejoué à chaque déploiement et restauration |
| API | Clé obligatoire comparée en temps constant, requêtes paramétrées, identifiants validés par expression régulière, limites de pagination |
| Réseau privé (option) | `enable_private_endpoints` ajoute des Private Endpoints et des zones DNS privées ; `lock_public_access` interdit alors l'accès public, avec garde-fous |
| Artefact | `archive_file` exclut les `.env.local`, les tests et les fichiers de développement |
| Chaîne d'approvisionnement | Versions épinglées, dbt-core fixé à 1.8.8 (dbt-postgres 1.8 n'impose pas de borne haute et installerait dbt-core 2.x), Dependabot, Trivy sur les images, gitleaks et pre-commit |
| Audit | Journaux d'audit du Key Vault envoyés vers Log Analytics |
| State Terraform | Storage dédié, versionné. Le state contient les secrets : ne pas le partager |

Limites assumées :

- Les clés d'accès du storage account ne sont pas désactivées, car le provider Terraform les utilise pour créer containers et blobs. L'application ne les utilise pas.
- Sans `enable_private_endpoints`, le Key Vault et le Storage restent joignables par leur point d'accès public (protégés par l'authentification Entra ID).
- L'API n'a pas de limitation de débit par client.
- Le port 80 ouvert à Internet est le prix du certificat automatique (voir l'[ADR 0006](docs/adr/0006-https-avec-caddy.md)).

## 17. Développement local

La plateforme complète tourne sur votre poste, avec Azurite à la place du Data Lake Azure : aucun compte ni coût Azure.

```bash
make local-up          # génère app/deploy/.env.local, construit et démarre tout
make local-trigger     # déclenche le pipeline principal
make local-logs        # suit les logs
make local-down        # arrête en conservant les données
make local-reset       # arrête et supprime les données
```

Les URLs locales sont Airflow `http://localhost:8080`, Grafana `http://localhost:3000`, Streamlit `http://localhost:8501`, API `http://localhost:8000/docs`. Les mots de passe et la clé d'API sont dans `app/deploy/.env.local`, généré avec des secrets aléatoires et exclu de Git. En local, HTTPS, Loki, node-exporter et cAdvisor ne sont pas démarrés (les cibles correspondantes apparaissent donc hors ligne dans Prometheus).

Le code accepte aussi la chaîne de connexion `UseDevelopmentStorage=true` des TP et la convertit en chaîne Azurite standard, car le SDK Azure v12 ne gère pas ce raccourci.

## 18. Tests et qualité

```bash
make setup-dev         # environnements Python pour les tests et pour dbt
make test              # lint, câblage Terraform, tests unitaires, DAGs, API, dashboards, documentation
make e2e               # test d'intégration complet dans des conteneurs jetables
```

`make e2e` supprime et recrée les schémas de la base : il utilise donc ses propres conteneurs (PostgreSQL sur le port 55432, Azurite sur 10100), jamais ceux de `make local-up`. Il nécessite Docker et les clients PostgreSQL (`psql`, `pg_dump`, `pg_restore`).

### Ce qui est testé

| Niveau | Contenu |
|---|---|
| Unitaires (ingestion) | Chemins du lac, conversion en lignes, validation, statuts qualité, backfill (alignement horaire, exclusion de l'heure courante), sentiment (RSS, Atom, entités XML malveillantes, faux positifs de mots-clés), prévisions (bornes, repli), Parquet |
| API | Authentification, validation des entrées, requêtes paramétrées, sérialisation des nombres |
| DAGs | Structure, ordre des tâches, absence de cycle, planification, sélections dbt identiques à celles de l'e2e (avec un Airflow simulé) |
| Dashboards | UID uniques, datasources existantes, absence de chevauchement, JSON à jour par rapport au générateur |
| Terraform | Vérificateur de câblage (variables, arguments de modules, sorties, références) lui-même testé par injection de fautes |
| Intégration (e2e) | Pipeline sur PostgreSQL 16, Azurite et dbt 1.8.8 réels : idempotence, dbt, détection d'une anomalie injectée sans faux positif, exports Parquet relus, backfill, sentiment, prévisions et backtest, API sur base réelle, rôles en lecture seule, toutes les requêtes SQL des dashboards avec le rôle de lecture, requêtes des exporters, cycle `pg_dump` et `pg_restore` |
| Documentation | Cibles `make`, alertes, variables, DAGs et dashboards cités dans ce README, liens internes, absence d'emoji et de tirets longs |

### Ce qui est vérifié par les outils officiels

Chaque configuration est validée par l'outil correspondant : `promtool` (Prometheus et règles), `amtool` (Alertmanager), `loki -verify-config`, `promtail -check-syntax`, `caddy validate`, `docker compose config` (production, profils et local), blackbox `--config.check`, statsd-exporter `--check-config`, `actionlint` (workflows), `shellcheck` (scripts) et `gitleaks` (secrets). Les 57 requêtes PromQL des dashboards sont validées par `promtool`, et le mapping StatsD a été testé avec de vrais paquets Airflow.

### Ce qui n'a pas pu être testé

Soyez conscient de ces limites avant le premier déploiement :

- `terraform validate`, `plan` et `apply` n'ont pas été exécutés (pas d'accès aux registres de providers ni à un abonnement). Le HCL est formaté et analysé, et le câblage est contrôlé statiquement, mais le premier `make up` reste le vrai test d'intégration Azure.
- Le build des images Docker (Airflow, API, Streamlit) n'a pas été exécuté. Les versions de dépendances ont été installées et testées dans des environnements isolés équivalents.
- Le rendu visuel des dashboards dans Grafana n'a pas été vérifié : les requêtes et la structure le sont, pas l'apparence.
- L'émission réelle des certificats Let's Encrypt, la Logic App de démarrage, le budget, les Private Endpoints, les snapshots via l'API Azure et le comportement exact de l'abonnement Students (régions, politiques) dépendent d'Azure.
- Le comportement de l'API publique de CoinGecko sans clé (limites de débit) et des flux RSS réels n'est pas garanti.

Il est normal d'ajuster quelques détails propres à votre abonnement lors du premier déploiement.

## 19. CI/CD

Les workflows de `.github/workflows` :

| Workflow | Déclenchement | Contenu |
|---|---|---|
| `ci` | Chaque push et pull request | Format, câblage et validation Terraform. Lint et tests Python. Test e2e avec PostgreSQL, Azurite et dbt. Validation de toutes les configurations de déploiement. gitleaks, Trivy (configuration Terraform et images), checkov. Build et scan des trois images, avec échec sur une vulnérabilité critique corrigeable |
| `terraform` | Pull request et lancement manuel | Plan commenté sur la pull request. Plan, apply ou destroy manuel par environnement, avec validation possible par un relecteur. Authentification Azure par OIDC, sans secret stocké |
| `cost` | Pull request sur `infra/` | Estimation du coût mensuel avec Infracost, si le secret `INFRACOST_API_KEY` existe |

Dependabot surveille les actions GitHub, les dépendances Python, les images Docker et les providers Terraform. Le fichier `.pre-commit-config.yaml` applique localement gitleaks, ruff, shellcheck, `terraform fmt`, le câblage Terraform et la cohérence des dashboards : `pip install pre-commit && pre-commit install`.

### Activer le déploiement GitHub Actions

Le déploiement par GitHub demande une application Entra ID, ce qu'un abonnement Students n'autorise pas toujours. Si c'est possible chez vous :

```bash
make bootstrap
tools/setup_github_oidc.sh <organisation>/<depot> dev prod
```

Le script crée l'application, les identifiants fédérés, les rôles nécessaires (dont `User Access Administrator`, que Terraform exige pour créer des role assignments) et affiche les commandes `gh variable set` à exécuter. Créez ensuite les environnements GitHub `dev` et `prod`, avec une validation manuelle pour `prod`. Sans ces variables, les jobs de déploiement sont simplement ignorés, et `make deploy` reste la méthode de référence.

## 20. Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| `ALLOWED_IP introuvable` | `api.ipify.org` injoignable | `make deploy ALLOWED_IP=x.x.x.x` |
| Services inaccessibles depuis le navigateur | IP différente de `allowed_ip` | `make deploy ALLOWED_IP=<votre IP>` |
| `ERR_CONNECTION_RESET` sur HTTPS, logs Caddy avec `forbidden domain "example.com"` | `alert_email` est une adresse `@example.com`, refusée par Let's Encrypt | Mettre une vraie adresse dans `infra/envs/dev/terraform.tfvars`, puis `make deploy ALLOWED_IP=<IP de votre PC>` (la VM est recréée) |
| `Connection timed out` en SSH | IP différente de `allowed_ip`, VM éteinte ou `enable_ssh = false` | Voir le [dépannage SSH](#dépannage-ssh) |
| `Permission denied (publickey)` | Mauvaise clé ou mauvais utilisateur | `make ssh-key`, puis `ssh -i ~/.ssh/cryptopulse-dev cpadmin@<IP>` |
| `AuthorizationFailed` ou `MissingSubscriptionRegistration` | Resource provider non enregistré | `make providers`, attendre quelques minutes |
| Taille de VM ou région refusée | Politique de l'abonnement Students | Changer `vm_size` ou `location` |
| Erreur sur le budget | API de budgets non disponible pour cette offre | `monthly_budget = 0` |
| Navigateur : certificat invalide ou erreur TLS | Certificat pas encore émis | Attendre 2 à 3 minutes ; `docker compose -p cryptopulse logs caddy` sur la VM |
| Let's Encrypt refuse l'émission | Limite de débit après plusieurs recréations | Attendre, ou utiliser `enable_https = false` en attendant |
| Airflow indisponible après `apply` | Build Docker en cours | `sudo journalctl -u cryptopulse-sync -f` sur la VM, attendre 10 à 15 minutes |
| Erreurs 401 ou 403 dans `journalctl` | Droits RBAC pas encore propagés | Rien à faire, le timer réessaie toutes les 5 minutes |
| Panneaux Grafana PostgreSQL vides | Tables pas encore créées | Déclencher `cryptopulse_pipeline`, puis `cryptopulse_backfill` |
| Panneaux sentiment ou prévisions vides | DAG pas encore exécuté | Attendre `cryptopulse_sentiment` (heure + 20 min) ou la nuit pour `cryptopulse_forecast` |
| Panneaux Prometheus `No data` | Premières minutes après le démarrage | Attendre 2 à 3 collectes |
| Dashboard Logs vide | `enable_logging = false` | Activer la variable et redéployer |
| Grafana : erreur de datasource PostgreSQL | Rôle `monitoring_ro` absent | `sudo systemctl start cryptopulse-sync` |
| `LowMemory` récurrente | 4 Go de RAM sous charge | `enable_logging = false` ou `Standard_B2ms` |
| `DataStale` après l'extinction nocturne | VM éteinte plus de 3 heures | Comportement attendu en dev, ajuster `FRESHNESS_MAX_HOURS` si besoin |
| Tâche `ingest_prices` en erreur 429 | Limite de débit de CoinGecko | Airflow réessaie 2 fois à 5 minutes d'écart |
| `terraform apply` échoue sur `lock_public_access` | Garde-fou | Activer `enable_private_endpoints` et renseigner `deployer_ip` |

Les procédures détaillées par alerte et les opérations courantes sont dans le [runbook](docs/runbook.md).

## 21. Limites et évolutions

- **Disponibilité** : une seule VM, sans haute disponibilité. La reprise repose sur les sauvegardes et la reconstruction par Terraform. Pour une vraie production, viser AKS ou Container Apps, PostgreSQL Flexible Server et un Airflow avec CeleryExecutor ou KubernetesExecutor.
- **Prévisions** : le modèle est volontairement simple. Le backtest affiché dans les données montrera souvent des performances proches d'une marche aléatoire, ce qui est un résultat normal pour des cryptomonnaies.
- **Sentiment** : VADER est un lexique anglais, sans compréhension du contexte financier. Un modèle spécialisé améliorerait la qualité, au prix de la mémoire.
- **API** : pas de limitation de débit par client ni de gestion de plusieurs clés. À ajouter derrière Caddy ou avec un API Management si elle devient publique.
- **Sources** : l'API CoinGecko est utilisée sans clé, avec les limites correspondantes. Une clé peut être ajoutée sans changer l'architecture.
- **Authentification de Grafana** : un mot de passe administrateur unique. Une intégration SSO Entra ID est une évolution naturelle, non incluse.
- **Logs** : seuls les conteneurs sont collectés. Les journaux systemd de la VM (synchronisation, sauvegarde) restent consultables par `journalctl`.
- **Snapshots** : non cohérents au niveau applicatif. La sauvegarde logique reste la référence.
- **Données** : l'historique profond au-delà de 90 jours est quotidien, pas horaire.

## 22. Documentation complémentaire

| Document | Contenu |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Diagrammes Mermaid : infrastructure, services, flux de données, séquence de déploiement, planning |
| [docs/runbook.md](docs/runbook.md) | Exploitation : accès, opérations, sauvegarde et restauration, rotation des secrets, playbooks par alerte, test de restauration |
| [docs/adr/README.md](docs/adr/README.md) | Onze décisions d'architecture avec contexte, alternatives et conséquences |

## 23. Captures d'écran

Cette section illustre le résultat du déploiement. Les images de `docs/screenshots/` sont des **placeholders gris** : remplacez-les par vos propres captures, en gardant exactement le même nom de fichier pour que le README les affiche sans autre modification.


### 1. Fin de make up : sorties Terraform


### 2. Ressources Azure déployées


### 3. Connexion SSH et conteneurs en service


### 4. Airflow : les 4 DAGs


### 5. Grafana : CryptoPulse, Marché


### 6. Grafana : CryptoPulse, Pipeline et qualité


### 7. Grafana : CryptoPulse, Infrastructure et logs


### 8. Dashboard Streamlit


### 9. API : documentation interactive


### 10. Key Vault : liste des secrets


## 24. Licence et auteur

Projet distribué sous licence MIT (voir [LICENSE](LICENSE)). Auteur : Pape Lo, cours DataOps, année 2025 - 2026.
