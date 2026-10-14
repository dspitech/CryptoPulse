# 0002. PostgreSQL en conteneur plutôt que Flexible Server

Statut : acceptée

## Contexte

Il faut un entrepôt relationnel multi-écrivains (Airflow, dbt, API, Grafana), à la place de SQLite utilisé dans les TP. Azure Database for PostgreSQL Flexible Server est souvent restreint par région ou par politique sur les abonnements Students, et son coût minimal dépasse celui du reste de la plateforme.

## Décision

PostgreSQL 16 tourne en conteneur sur la VM. Ses données sont sur un disque managé dédié, monté sur `/data`, qui survit à la recréation de la VM. Le réseau Docker est la seule voie d'accès : le port 5432 n'est jamais publié en production.

## Alternatives écartées

- **Flexible Server** : meilleure exploitation (sauvegardes gérées, haute disponibilité) mais risque de blocage à l'abonnement et coût supérieur.
- **SQLite** : un seul écrivain, inadapté à Airflow et à plusieurs lecteurs.

## Conséquences

- Les sauvegardes sont à notre charge (ADR 0007).
- Les montées de version majeure de PostgreSQL demandent une migration manuelle.
- Migrer vers Flexible Server plus tard est simple : `pg_dump` puis `pg_restore`, et changement de l'hôte dans la configuration.
