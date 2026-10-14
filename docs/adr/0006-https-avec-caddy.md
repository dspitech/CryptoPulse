# 0006. HTTPS avec Caddy et défi ACME HTTP-01

Statut : acceptée

## Contexte

Airflow, Grafana, l'API et le dashboard étaient en HTTP clair. Il faut du TLS valide sans acheter de domaine ni gérer de certificats à la main.

## Décision

L'IP publique reçoit une étiquette DNS Azure (`<label>.norwayeast.cloudapp.azure.com`). Caddy obtient et renouvelle seul les certificats Let's Encrypt par défi HTTP-01. Les services n'écoutent plus que sur 127.0.0.1 ; Caddy publie 443 (Grafana), 8443 (Airflow), 9443 (dashboard) et 8444 (API). Le port 80 est le seul ouvert à Internet, car le défi HTTP-01 l'exige : Caddy n'y répond qu'avec le défi ou une redirection. Tous les autres ports restent limités à l'IP autorisée par le NSG. Le défi TLS-ALPN est désactivé pour ne pas dépendre du port 443 ouvert à tous.

## Alternatives écartées

- **Défi DNS-01** : impossible sans zone DNS contrôlée (le sous-domaine cloudapp appartient à Azure).
- **Certificat auto-signé** : alertes de sécurité dans tous les navigateurs.
- **Application Gateway ou Front Door** : coût élevé pour ce périmètre.

## Conséquences

- Un port ouvert à Internet (80), au contenu inoffensif, est le prix du certificat automatique.
- Let's Encrypt impose des limites de débit : éviter les cycles destroy et apply répétés avec un même nom.
- `enable_https = false` revient à HTTP direct sur les ports d'origine.
