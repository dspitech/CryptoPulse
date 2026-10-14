# 0004. Identités managées et Key Vault pour tous les secrets

Statut : acceptée

## Contexte

Les TP stockaient un mot de passe dans `variables.tf`, copiaient la connection string du Storage à la main et la saisissaient dans l'interface d'Airflow.

## Décision

Terraform génère tous les secrets (`random_password`, `random_id`, clé SSH) et les écrit dans un Key Vault en mode RBAC. Une identité managée affectée par l'utilisateur est créée avant la VM. Elle a `Storage Blob Data Contributor` sur le Data Lake, `Key Vault Secrets User` sur le coffre et, si activé, `Disk Snapshot Contributor` sur le resource group. La VM lit ses secrets au déploiement, via le service de métadonnées, et les écrit dans un fichier `runtime.env` de permissions 600. Aucune clé de stockage n'est utilisée par l'application.

## Alternatives écartées

- **Variables d'environnement dans Terraform** : les secrets passeraient par le code et la ligne de commande.
- **Identité affectée au système** : créée avec la VM, donc non attribuable avant le premier démarrage.

## Conséquences

- Le state Terraform contient les secrets : le storage du state est dédié, versionné, et ne doit jamais être partagé.
- Un délai de propagation RBAC existe : un `time_sleep` de 60 secondes et la reprise automatique du timer le couvrent.
- Rotation : la clé d'API et les mots de passe des rôles en lecture seule se renouvellent seuls ; les mots de passe déjà inscrits dans une base existante (PostgreSQL, Airflow, Grafana) demandent une action manuelle, décrite dans le runbook.
