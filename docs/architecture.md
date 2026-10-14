# Architecture de CryptoPulse

Ce document complète le README avec des diagrammes. Les décisions qui les justifient sont dans [docs/adr](adr/README.md).

## Vue d'ensemble de l'infrastructure

```mermaid
flowchart TB
    dev["Poste local ou Cloud Shell<br/>make up"] -->|terraform apply| azure
    gh["GitHub Actions<br/>OIDC, plan, apply"] -.->|optionnel| azure

    subgraph azure["Azure norwayeast (un resource group par environnement)"]
        kv["Key Vault<br/>secrets, cle SSH"]
        id["Identite managee<br/>RBAC"]
        lake["Data Lake ADLS Gen2<br/>bronze, silver, gold, artifacts"]
        mon["Azure Monitor<br/>Log Analytics, alertes email"]
        logic["Logic App<br/>demarrage 07h00"]
        subgraph vnet["VNet et NSG : IP autorisee uniquement"]
            vm["VM Ubuntu 24.04 Standard_B2s<br/>cloud-init, Docker Compose"]
            disk[("Disque de donnees<br/>snapshots hebdomadaires")]
        end
        pe["Private Endpoints<br/>optionnel"]
    end

    vm --- disk
    vm -->|identite managee| id
    id --> kv
    id --> lake
    vm -.->|trafic prive| pe
    pe -.-> kv
    pe -.-> lake
    logic -->|start| vm
    mon -->|surveille| vm
```

## Services sur la VM

```mermaid
flowchart LR
    user(("Utilisateur<br/>IP autorisee"))
    subgraph vm["VM : Docker Compose"]
        caddy["Caddy<br/>HTTPS Let's Encrypt"]
        subgraph app["Application"]
            airflow["Airflow<br/>webserver + scheduler"]
            api["API FastAPI"]
            st["Streamlit"]
            pg[("PostgreSQL 16")]
        end
        subgraph obs["Observabilite"]
            prom["Prometheus"]
            am["Alertmanager"]
            graf["Grafana"]
            loki["Loki + Promtail"]
            exp["Exporters<br/>node, cAdvisor, postgres,<br/>statsd, blackbox"]
        end
    end
    user -->|443, 8443, 9443, 8444| caddy
    caddy --> graf
    caddy --> airflow
    caddy --> st
    caddy --> api
    airflow --> pg
    api --> pg
    st --> pg
    exp --> prom
    airflow -->|statsd| exp
    prom --> am
    prom --> graf
    pg --> graf
    loki --> graf
```

## Flux de données

```mermaid
flowchart LR
    cg["CoinGecko<br/>prix, historique"] --> ing
    rss["Flux RSS<br/>actualites"] --> sen
    fg["Fear and Greed<br/>alternative.me"] --> sen

    subgraph airflow["Airflow : 4 DAGs"]
        ing["cryptopulse_pipeline<br/>horaire"]
        bf["cryptopulse_backfill<br/>manuel"]
        sen["cryptopulse_sentiment<br/>horaire a H+20"]
        fc["cryptopulse_forecast<br/>quotidien"]
    end

    bf --> bronze
    ing --> bronze[("bronze<br/>JSON brut")]
    sen --> bronze
    bronze --> raw[("raw<br/>PostgreSQL")]
    raw --> dbt["dbt<br/>staging puis marts"]
    dbt --> marts[("marts")]
    marts --> silver[("silver<br/>Parquet")]
    marts --> gold[("gold<br/>Parquet, rapports, sauvegardes")]
    marts --> fc
    fc --> ops[("ops.forecast_history")]
    ops --> dbt
    marts --> consumers["Grafana, Streamlit, API"]
```

## Déploiement : de `make up` à la plateforme en service

```mermaid
sequenceDiagram
    actor U as Utilisateur
    participant T as Terraform
    participant A as Azure
    participant V as VM (cloud-init)
    participant L as Data Lake
    participant K as Key Vault

    U->>T: make up
    T->>A: reseau, stockage, Key Vault, identite
    T->>K: secrets generes (mots de passe, cle API, cle SSH)
    T->>L: publie app.zip (dossier app/)
    T->>A: cree la VM avec cloud-init
    A->>V: premier demarrage
    V->>V: installe Docker, monte le disque de donnees
    V->>L: telecharge app.zip (identite managee)
    V->>K: lit les secrets (identite managee)
    V->>V: docker compose up, cree les roles PostgreSQL
    loop toutes les 5 minutes
        V->>L: l'ETag de app.zip a-t-il change ?
        L-->>V: oui : synchronisation et redeploiement
    end
```

## Planning des traitements (UTC)

| Heure | Traitement |
|---|---|
| Chaque heure, minute 00 | `cryptopulse_pipeline` : ingestion, validation, chargement, dbt, export Parquet, qualité |
| Chaque heure, minute 20 | `cryptopulse_sentiment` : actualités, Fear and Greed, modèles dbt de sentiment |
| 02h30 | `cryptopulse_forecast` : prévisions à 7 jours, précision des prévisions passées |
| 03h30 | Sauvegarde PostgreSQL vers `gold/backups/` ; snapshot du disque si le dernier a plus de 6 jours |
| 07h00 (dev) | Démarrage automatique de la VM par la Logic App |
| 21h00 (dev) | Extinction automatique de la VM |
| Toutes les 5 minutes | Synchronisation de l'artefact de déploiement |
