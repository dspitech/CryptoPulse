# Décisions d'architecture (ADR)

Chaque décision structurante est consignée avec son contexte, ses alternatives et ses conséquences. Une décision remplacée n'est pas supprimée : elle est marquée comme remplacée et renvoie vers la nouvelle.

| N° | Décision | Statut |
|---|---|---|
| [0001](0001-vm-docker-compose-plutot-qu-aks.md) | VM et Docker Compose plutôt qu'AKS | Acceptée |
| [0002](0002-postgresql-en-conteneur.md) | PostgreSQL en conteneur plutôt que Flexible Server | Acceptée |
| [0003](0003-deploiement-par-artefact.md) | Déploiement par artefact Blob et timer systemd | Acceptée |
| [0004](0004-identites-managees-et-key-vault.md) | Identités managées et Key Vault pour tous les secrets | Acceptée |
| [0005](0005-supervision-prometheus-grafana.md) | Supervision Prometheus et Grafana, dashboards générés | Acceptée |
| [0006](0006-https-avec-caddy.md) | HTTPS avec Caddy et défi ACME HTTP-01 | Acceptée |
| [0007](0007-sauvegardes.md) | Sauvegardes : pg_dump quotidien et snapshots du disque | Acceptée |
| [0008](0008-previsions-arima.md) | Prévisions ARIMA et leurs limites | Acceptée |
| [0009](0009-sources-complementaires.md) | Sources complémentaires et respect des contenus | Acceptée |
| [0010](0010-roles-postgresql-et-api.md) | Rôles PostgreSQL en lecture seule et API dédiée | Acceptée |
| [0011](0011-strategie-de-tests.md) | Stratégie de tests : services réels et validation des configurations | Acceptée |
