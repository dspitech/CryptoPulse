# 0005. Supervision Prometheus et Grafana, dashboards générés

Statut : acceptée

## Contexte

La plateforme doit être observable de bout en bout : machine, conteneurs, base, Airflow, qualité des données et métier. Les dashboards créés à la main dans l'interface ne sont ni versionnés ni reproductibles.

## Décision

Prometheus collecte des exporters standards. Les métriques d'Airflow passent par StatsD puis statsd-exporter (avec une liste fermée de métriques). Les métriques métier (fraîcheur, anomalies, prix, sauvegardes) sortent de requêtes SQL de postgres-exporter et du collecteur textfile de node-exporter. Grafana est entièrement provisionné : datasources et cinq dashboards au format JSON, générés par `tools/generate_dashboards.py`. Les tests vérifient les UID, les datasources et l'absence de chevauchement, et l'e2e exécute toutes les requêtes SQL des dashboards avec le rôle en lecture seule.

## Alternatives écartées

- **Dashboards écrits à la main en JSON** : illisibles et sujets aux erreurs de placement.
- **Azure Monitor seul** : peu adapté aux métriques applicatives et métier.
- **Stack managée (Managed Grafana, Azure Monitor for Prometheus)** : coût et complexité supérieurs sur ce périmètre.

## Conséquences

- Charge mémoire supplémentaire sur la VM, bornée par des limites de conteneurs.
- Modifier un dashboard passe par le générateur, puis `make dashboards` : la CI vérifie que le JSON versionné correspond.
- Le rendu visuel final dans Grafana n'est pas testé automatiquement ; seules les requêtes et la structure le sont.
