# 0001. VM et Docker Compose plutôt qu'AKS

Statut : acceptée

## Contexte

L'abonnement Azure for Students n'autorise pas AKS. La plateforme doit malgré tout être entièrement déployée par Terraform, sans étape manuelle, et rester proche d'un contexte professionnel.

## Décision

Une VM Ubuntu `Standard_B2s` héberge tous les services avec Docker Compose. cloud-init installe Docker et un timer systemd, qui déploie l'application (voir ADR 0003). Les services applicatifs et d'observabilité sont des conteneurs, ce qui les rend portables vers Kubernetes.

## Alternatives écartées

- **AKS** : indisponible sur l'abonnement.
- **Container Apps** : bonne option, mais les volumes et les services avec état (PostgreSQL, Prometheus) y sont peu adaptés.
- **Plusieurs VM** : plus de coût et de complexité réseau pour un volume de données très faible.

## Conséquences

- Une seule machine : pas de haute disponibilité. La reprise repose sur les sauvegardes (ADR 0007) et sur la reconstruction par Terraform.
- Empreinte mémoire à surveiller sur 4 Go de RAM : limites par conteneur, swap de 4 Go, composants optionnels (Loki) désactivables.
- Le passage à AKS ou à Container Apps demandera de réécrire le déploiement, pas les applications.
