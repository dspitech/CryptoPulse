# 0007. Sauvegardes : pg_dump quotidien et snapshots du disque

Statut : acceptée

## Contexte

PostgreSQL tourne dans un conteneur : sans stratégie de sauvegarde, la perte du disque ou une mauvaise manipulation détruirait le warehouse. Le Data Lake garde les données brutes, mais pas l'historique des prévisions ni des contrôles qualité.

## Décision

Une sauvegarde `pg_dump` au format custom, vérifiée par `pg_restore --list`, est envoyée chaque nuit dans `gold/backups/` et conservée 7 jours sur la VM et 30 à 90 jours dans le Data Lake (règle de cycle de vie). Un snapshot incrémental du disque de données est créé chaque semaine par la VM, via l'API Azure et son identité managée, et les 4 derniers sont conservés. Le résultat est publié en métriques Prometheus, avec alertes. La restauration se fait par `cryptopulse-restore`, testée dans l'e2e avec les mêmes options de `pg_dump` et `pg_restore`.

## Alternatives écartées

- **Azure Backup (Recovery Services Vault)** : plus complet, mais coûteux et délicat à détruire proprement avec Terraform.
- **Réplication PostgreSQL** : inutile pour un volume aussi faible, et ne protège pas des erreurs humaines.

## Conséquences

- Le RPO est de 24 heures au pire pour la base ; le disque entier peut remonter à une semaine.
- Les snapshots ne sont pas cohérents au niveau applicatif : la sauvegarde logique reste la référence.
- Un test de restauration régulier reste indispensable (voir le runbook).
