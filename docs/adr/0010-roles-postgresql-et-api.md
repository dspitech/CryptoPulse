# 0010. Rôles PostgreSQL en lecture seule et API dédiée

Statut : acceptée

## Contexte

Grafana, postgres-exporter et une API de données ont besoin de lire le warehouse, sans jamais pouvoir le modifier ni lire des données qu'ils n'ont pas à connaître.

## Décision

Deux rôles en lecture seule (`default_transaction_read_only`) sont créés par un script SQL idempotent, rejoué à chaque déploiement et à chaque restauration. `monitoring_ro` (Grafana, exporter) lit tout. `api_ro` ne lit que les schémas `marts` et `ops`, avec des privilèges par défaut qui survivent aux tables recréées par dbt, un délai maximal de requête de 10 secondes et 10 connexions au plus. L'API, protégée par une clé et limitée à des requêtes paramétrées, expose les marts sans jamais toucher aux données brutes.

## Alternatives écartées

- **Un seul rôle pour tous** : une faille dans l'API donnerait l'accès en écriture au warehouse.
- **Vues d'exposition dédiées** : plus de modèles à maintenir pour un bénéfice faible ici.

## Conséquences

- La rotation des mots de passe de ces deux rôles est automatique, puisque le script les réapplique.
- Ajouter un nouveau consommateur revient à ajouter un rôle dans `roles.sql`.
- Il n'y a pas de limitation de débit par client sur l'API : à ajouter derrière Caddy si elle devient publique.
