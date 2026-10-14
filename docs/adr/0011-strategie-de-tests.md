# 0011. Stratégie de tests : services réels et validation des configurations

Statut : acceptée

## Contexte

L'essentiel du risque d'un projet DataOps se trouve dans l'intégration (SQL, formats, droits, déploiement) plus que dans la logique pure. Terraform ne peut pas être exécuté sans abonnement Azure, ni dans tous les environnements de développement.

## Décision

Trois niveaux. Les tests unitaires couvrent la logique pure (formats, parsing, prévisions, API avec base simulée, structure des DAGs avec Airflow simulé). Un test d'intégration utilise PostgreSQL 16, Azurite et dbt 1.8.8 réels : il exécute le pipeline, les modèles dbt, les exports Parquet, la détection d'anomalies sur une série avec une anomalie injectée, l'API, toutes les requêtes SQL des dashboards avec le rôle en lecture seule, les requêtes des exporters et un cycle sauvegarde et restauration. Enfin, chaque fichier de configuration est validé par l'outil officiel correspondant (promtool, amtool, Loki, Promtail, Caddy, docker compose, actionlint, shellcheck, gitleaks), et un vérificateur de câblage contrôle statiquement les variables, modules et sorties Terraform.

## Alternatives écartées

- **Tests uniquement unitaires** : n'auraient pas détecté les défauts réels trouvés pendant le développement (nombres sérialisés en texte par l'API, dbt-core 2.x installé en silence, éléments XML évalués comme faux).
- **Terraform avec un provider simulé** : peu fiable et coûteux à maintenir.

## Conséquences

- Ce qui reste hors de portée des tests locaux est listé explicitement dans le README : `terraform validate` et `apply`, le build des images, le rendu visuel de Grafana, l'émission réelle des certificats, la Logic App, le budget, les Private Endpoints.
- Le test e2e utilise des conteneurs jetables, jamais l'environnement local de développement, car il supprime et recrée les schémas.
