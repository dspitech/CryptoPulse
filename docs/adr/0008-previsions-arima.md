# 0008. Prévisions ARIMA et leurs limites

Statut : acceptée

## Contexte

Le projet gagne en intérêt avec une dimension prédictive, mais les cours des cryptomonnaies sont très peu prévisibles et les ressources de la VM sont limitées.

## Décision

Un modèle ARIMA(1,1,1) est ajusté chaque jour sur le logarithme des clôtures journalières complètes (minimum 21 jours) avec `statsmodels`, et prévoit 7 jours avec un intervalle à 80 %. Si l'ajustement échoue, une marche aléatoire prend le relais et le modèle utilisé est enregistré. Chaque prévision est historisée dans `ops.forecast_history`, et un modèle dbt la compare aux clôtures réelles (erreur moyenne et taux de couverture de l'intervalle) pour afficher honnêtement sa fiabilité.

## Alternatives écartées

- **Prophet** : dépendances lourdes (Stan) et mémoire importante sur 4 Go.
- **Modèles de deep learning** : disproportionnés pour une série quotidienne courte.

## Conséquences

- Les prévisions sont une illustration statistique, jamais un conseil financier : le README et les panneaux Grafana l'indiquent.
- La précision mesurée par le backtest sera souvent proche d'une marche aléatoire, ce qui est un résultat normal à documenter.
- Le modèle se remplace sans toucher au reste : seule la fonction `forecast_series` change.
