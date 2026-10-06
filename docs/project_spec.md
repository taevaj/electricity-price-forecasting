# Spécification V1

- Marché : France day-ahead.
- Cible : prix de clearing horaire en EUR/MWh.
- Forecast origin : 11:00 Europe/Paris le jour D-1.
- Horizon : toutes les périodes du jour D, soit 23, 24 ou 25 selon le changement d'heure.
- Index de calcul : UTC ; heure métier : Europe/Paris.
- Période : du 1er janvier 2022 au 30 septembre 2025 inclus.
- Usage : recherche et portfolio, sans décision de trading réelle.

## Contrat anti-leakage

Une feature est admissible uniquement si `available_at_utc <= forecast_origin_utc`. Les observations réalisées sont marquées `diagnostic_only`. Les flags négatif/spike servent uniquement à l'analyse. Le seuil de spike est appris sur le train. Les lags J-1/J-7 sont construits par date et période locale sans supposer 24 lignes par jour.

## Découpage

- Train : `[2022-01-01, 2024-01-01)`.
- Validation : `[2024-01-01, 2025-01-01)`.
- Test : `[2025-01-01, 2025-10-01)`.

Les intervalles sont semi-ouverts et le test reste fermé jusqu'au gel du pipeline.
