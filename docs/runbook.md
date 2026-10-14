# Runbook d'exploitation

Ce guide s'adresse à la personne qui exploite la plateforme. Toutes les commandes `make` se lancent depuis la racine du dépôt ; celles qui commencent par `sudo` ou `docker` se lancent sur la VM.

## Sommaire

1. [Accès à la VM](#1-accès-à-la-vm)
2. [Vérifier l'état de la plateforme](#2-vérifier-létat-de-la-plateforme)
3. [Opérations courantes](#3-opérations-courantes)
4. [Sauvegardes et restauration](#4-sauvegardes-et-restauration)
5. [Rotation des secrets](#5-rotation-des-secrets)
6. [Changements d'infrastructure](#6-changements-dinfrastructure)
7. [Playbooks par alerte](#7-playbooks-par-alerte)
8. [Procédure de test de restauration](#8-procédure-de-test-de-restauration)

## 1. Accès à la VM

```bash
make ssh-key                          # écrit ~/.ssh/cryptopulse-dev depuis Key Vault
make output                           # affiche la commande SSH et les URLs
ssh -i ~/.ssh/cryptopulse-dev cpadmin@<IP_VM>
make tunnel                           # Prometheus sur localhost:9090, Alertmanager sur localhost:9093
```

SSH n'est ouvert que depuis l'IP autorisée (`allowed_ip`) et peut être désactivé avec `enable_ssh = false` (cas de `prod`). Sans SSH, l'exploitation passe par le portail Azure (commande d'exécution) ou par une réactivation temporaire.

Si votre IP publique change, relancez `make deploy ALLOWED_IP=<nouvelle IP>` : seul le NSG est modifié.

## 2. Vérifier l'état de la plateforme

Sur la VM :

```bash
cloud-init status --wait                              # fin de l'initialisation (premier démarrage)
sudo journalctl -u cryptopulse-sync -n 50 --no-pager  # dernier déploiement
systemctl list-timers 'cryptopulse-*'                 # prochains passages de la synchronisation et de la sauvegarde
docker compose -p cryptopulse ps                      # état des conteneurs
free -h && df -h / /data                              # mémoire et disques
```

Depuis Grafana, le dashboard **CryptoPulse : Pipeline et qualité** donne la vue la plus rapide : fraîcheur des données, contrôles en échec, alertes actives, sauvegardes.

## 3. Opérations courantes

Sur la VM, toutes les commandes Compose utilisent le même préfixe. Pour l'abréger :

```bash
alias cp-compose='docker compose -p cryptopulse -f /opt/cryptopulse/app/deploy/docker-compose.yml --env-file /opt/cryptopulse/runtime.env'
```

| Besoin | Commande |
|---|---|
| Logs d'un service | `cp-compose logs --tail=200 -f airflow-scheduler` |
| Redémarrer un service | `cp-compose restart grafana` |
| Forcer un redéploiement | `sudo systemctl start cryptopulse-sync` (ou `sudo bash /opt/cryptopulse/app/deploy/deploy.sh` pour relire les secrets) |
| Déclencher le pipeline | `cp-compose exec airflow-scheduler airflow dags trigger cryptopulse_pipeline` |
| Charger l'historique | `cp-compose exec airflow-scheduler airflow dags trigger cryptopulse_backfill --conf '{"days": 90}'` |
| Relancer une tâche en échec | Interface Airflow : clic sur la tâche, puis Clear |
| Ouvrir un shell SQL | `cp-compose exec postgres psql -U cryptopulse -d cryptopulse` |
| Lancer dbt à la main | `cp-compose exec airflow-scheduler bash -c 'cd /opt/airflow/dbt && /home/airflow/dbt-venv/bin/dbt build --project-dir . --profiles-dir .'` |

Après un premier déploiement, déclenchez `cryptopulse_backfill` : les moyennes mobiles, la volatilité, la détection d'anomalies et les prévisions ont besoin d'historique pour être pleinement utiles.

Les certificats HTTPS sont gérés seuls par Caddy. En cas de problème : `cp-compose logs caddy`. Un échec d'émission vient le plus souvent d'une limite de débit de Let's Encrypt ou d'un port 80 bloqué.

## 4. Sauvegardes et restauration

### Ce qui est sauvegardé

| Quoi | Quand | Où | Durée de conservation |
|---|---|---|---|
| Base `cryptopulse` (`pg_dump` au format custom) | Chaque nuit à 03h30 UTC | `gold/backups/AAAA/MM/JJ/` et `/data/backups` | 30 jours dev, 90 jours prod dans le Data Lake ; 7 jours sur la VM |
| Disque de données (snapshot incrémental) | Chaque semaine | Snapshots du resource group | 4 derniers |
| Données brutes (JSON) | À chaque ingestion | `bronze` | Illimitée (tier Cool après 30 jours) |

La base `airflow` (historique des exécutions) n'est pas sauvegardée : elle se reconstruit, et le warehouse s'alimente depuis `bronze`.

### Lancer une sauvegarde maintenant

```bash
sudo cryptopulse-backup
```

### Restaurer la base

```bash
sudo cryptopulse-restore latest            # dernière sauvegarde du Data Lake
sudo cryptopulse-restore backups/2026/10/09/cryptopulse-20261009T033000Z.dump
sudo cryptopulse-restore /data/backups/cryptopulse-20261009T033000Z.dump
sudo cryptopulse-restore --yes latest      # sans confirmation
```

Le script vérifie l'archive, arrête Airflow, le dashboard et l'API, restaure avec `--clean --if-exists --single-transaction`, réapplique les droits des rôles en lecture seule, puis redémarre les services. En cas d'échec, la transaction est annulée et les services restent arrêtés : relancez-les avec `cp-compose start airflow-scheduler airflow-webserver dashboard api`.

### Restaurer le disque entier depuis un snapshot

À utiliser si le disque de données est perdu ou corrompu.

```bash
az snapshot list -g rg-cryptopulse-dev --query "[?starts_with(name,'snap-cryptopulse-data-')].{n:name,t:timeCreated}" -o table
az disk create -g rg-cryptopulse-dev -n disk-data-restored --source snap-cryptopulse-data-<horodatage> --sku StandardSSD_LRS
```

Puis arrêter la VM, détacher l'ancien disque, attacher `disk-data-restored` au LUN 0 et démarrer la VM : le montage se fait par label `datadisk`. Ensuite, importez le nouveau disque dans Terraform (`terraform import`) ou revenez à la sauvegarde logique, plus simple.

### Reconstruire la VM sans perdre les données

Le disque de données est une ressource séparée : recréer la VM ne le supprime pas.

```bash
terraform -chdir=infra/envs/dev apply -replace='module.platform.module.compute.azurerm_linux_virtual_machine.this' -var allowed_ip=<IP>
```

La VM redémarre, remonte le disque par son label et redéploie l'application. Prévoir quelques minutes d'indisponibilité.

## 5. Rotation des secrets

Seuls certains secrets se renouvellent automatiquement, car les autres sont inscrits dans une base déjà initialisée.

| Secret | Rotation | Procédure |
|---|---|---|
| Clé d'API (`api-key`) | Automatique | `terraform apply -replace='module.platform.module.keyvault.random_password.api_key'` puis `sudo bash /opt/cryptopulse/app/deploy/deploy.sh` |
| Mot de passe de `monitoring_ro` et `api_ro` | Automatique | Même méthode avec `random_password.monitoring_db` ou `random_password.api_db` : `roles.sql` réapplique le mot de passe |
| Mot de passe de Grafana | Manuelle | Après changement dans Key Vault : `cp-compose exec grafana grafana cli admin reset-admin-password <nouveau>` |
| Mot de passe admin d'Airflow | Manuelle | `cp-compose exec airflow-scheduler airflow users reset-password -u admin` |
| Mot de passe `cryptopulse` de PostgreSQL | Manuelle | `ALTER ROLE cryptopulse PASSWORD '...'` dans `psql`, puis mise à jour dans Key Vault et `deploy.sh` |
| Clé Fernet d'Airflow | Délicate | Les connexions et variables chiffrées doivent être rechiffrées : suivre la documentation d'Airflow sur la rotation des clés Fernet |
| Clé SSH | Automatique | `terraform apply -replace='module.platform.tls_private_key.vm'` recrée la VM |

## 6. Changements d'infrastructure

| Changement | Action |
|---|---|
| Taille de la VM | Modifier `vm_size` dans `terraform.tfvars`, puis `make deploy`. La VM redémarre. |
| Ajouter une crypto | Modifier `coins`, puis `make deploy`. La VM est recréée (le cloud-init change) : prévoir une courte interruption. |
| Désactiver Loki | `enable_logging = false` puis `make deploy`. |
| Désactiver l'extinction nocturne | `auto_shutdown_time = ""` et `auto_start_time = ""`. |
| Passer en HTTP simple | `enable_https = false` : les services reviennent sur 8080, 3000, 8501 et 8000. |
| Verrouiller Key Vault et Storage | `enable_private_endpoints = true`, `deployer_ip = "<IP fixe>"`, `lock_public_access = true`. Le poste qui exécute Terraform doit conserver cette IP. |

## 7. Playbooks par alerte

| Alerte | Premier diagnostic | Action |
|---|---|---|
| TargetDown | Prometheus, onglet Status puis Targets : quelle cible, quel message d'erreur | Redémarrer le service concerné ; si la VM est en cause, voir `LowMemory` |
| HighCpuUsage | Dashboard Infrastructure, panneau CPU par service | Identifier le conteneur consommateur ; une exécution dbt ou une prévision ponctuelle est normale |
| LowMemory | `free -h`, `docker stats --no-stream` | Désactiver Loki (`enable_logging = false`) ou passer à `Standard_B2ms` |
| DataDiskAlmostFull | `du -sh /data/*` | Purger `/data/backups`, réduire la rétention de Prometheus, agrandir le disque (`data_disk_gb`) |
| RootDiskAlmostFull | `docker system df` | `docker image prune -a` puis `docker builder prune` |
| ServiceProbeFailing | Le panneau Disponibilité indique la cible | Consulter les logs du service ; pour l'API CoinGecko, attendre : c'est une dépendance externe |
| PostgresDown | `cp-compose ps postgres` puis `cp-compose logs postgres` | Redémarrer ; si le disque est corrompu, restaurer (section 4) |
| PostgresConnectionsHigh | `SELECT state, count(*) FROM pg_stat_activity GROUP BY 1;` | Redémarrer le service qui fuit les connexions |
| AirflowSchedulerHeartbeatMissing | `cp-compose logs airflow-scheduler` | `cp-compose restart airflow-scheduler` |
| AirflowTaskFailures | Interface Airflow, DAG et tâche en rouge, onglet Logs | Corriger la cause puis Clear sur la tâche |
| AirflowDagImportErrors | Interface Airflow, bandeau d'erreur en haut | Corriger l'erreur de syntaxe dans `app/airflow/dags` puis `make deploy` |
| DataStale | Dernier snapshot : `SELECT max(snapshot_ts) FROM raw.prices;` | Vérifier la VM (a-t-elle été éteinte ?), les logs de `ingest_prices`, l'état de l'API CoinGecko |
| DataMetricsAbsent | Logs de postgres-exporter | Vérifier que le rôle `monitoring_ro` existe ; relancer `deploy.sh` |
| QualityChecksFailing | Tableau Derniers contrôles qualité du dashboard Pipeline | Traiter la cause (table vide, prix invalides) puis relancer le DAG |
| PriceAnomalyDetected | Dashboard Marché, annotations rouges sur les courbes | Information de marché, pas une panne : vérifier qu'il ne s'agit pas d'une donnée source erronée |
| LargePriceMove | Dashboard Marché | Information de marché |
| DatabaseBackupMissing | `sudo journalctl -u cryptopulse-backup -n 50` | Corriger l'erreur affichée puis `sudo cryptopulse-backup` |
| DatabaseBackupMetricAbsent | `systemctl list-timers cryptopulse-backup.timer` | Vérifier que le timer est actif et que l'artefact est déployé |
| DiskSnapshotTooOld | Même journal | Vérifier le rôle `Disk Snapshot Contributor` de l'identité managée |
| ApiServerErrors, ApiHighLatency | `cp-compose logs api` | Vérifier PostgreSQL ; si le problème persiste, redémarrer l'API |
| LoggingStackDown | `cp-compose logs loki promtail` | Redémarrer, ou désactiver la pile si la mémoire manque |

## 8. Procédure de test de restauration

Une sauvegarde qui n'a jamais été restaurée n'est pas une sauvegarde. À faire une fois par trimestre, et après tout changement du schéma :

1. Lancer `sudo cryptopulse-backup` et vérifier que la métrique `cryptopulse_backup_last_success_timestamp_seconds` est à jour.
2. Noter le nombre de lignes : `SELECT count(*) FROM raw.prices;`.
3. Exécuter `sudo cryptopulse-restore latest` sur l'environnement `dev`.
4. Vérifier : même nombre de lignes, dashboards Grafana alimentés, `GET /v1/coins` de l'API valide, DAG `cryptopulse_pipeline` exécutable.
5. Consigner la date, la durée de la restauration et les écarts constatés.

Le test automatisé `test_18_backup_and_restore_roundtrip` valide en CI les options de `pg_dump` et `pg_restore`, mais pas la chaîne complète (envoi dans le Data Lake, arrêt des services) : seule cette procédure la vérifie.
