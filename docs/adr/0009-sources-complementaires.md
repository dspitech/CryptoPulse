# 0009. Sources complémentaires et respect des contenus

Statut : acceptée

## Contexte

Enrichir les analyses avec le sentiment du marché demande des sources externes, dont les conditions d'utilisation doivent être respectées.

## Décision

Les actualités viennent de flux RSS publics (CoinDesk, Cointelegraph, Decrypt par défaut, configurables). Seuls le titre, le lien, la source, la date et le score de sentiment sont stockés : le contenu des articles n'est pas conservé. Le score est calculé par VADER sur le titre et le résumé, localement, sans service payant. Le Fear and Greed Index vient d'alternative.me. Les flux XML sont analysés avec `defusedxml`, et une source en panne ne bloque pas les autres.

## Alternatives écartées

- **Récupération du texte complet des articles** : problèmes de droits et de volume.
- **Modèles de langage pour le sentiment** : coût, latence et dépendance externe pour un gain incertain sur des titres courts.

## Conséquences

- VADER est un lexique anglais : le sentiment est approximatif et ne comprend ni l'ironie ni le contexte financier.
- L'association article et crypto repose sur des mots-clés sans ambiguïté, et ignore volontairement des noms trop courants comme ada ou sol.
- L'API CoinGecko sans clé est limitée en débit ; une clé peut être ajoutée plus tard sans changer l'architecture.
