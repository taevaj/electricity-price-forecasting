# Electricity Price Forecasting — France Day-Ahead Market

Prévision des prix spot day-ahead de l'électricité en France, avec une
approche qui relie les fondamentaux physiques du système électrique
(demande, éolien, solaire, nucléaire, gaz, CO2) à la formation du prix, et
qui respecte une méthodologie de série temporelle sans data leakage.

> **État réel :** socle méthodologique en cours. Les données, modèles entraînés
> et résultats ne sont pas encore produits.

- [Spécification V1](docs/project_spec.md)
- [Fondamentaux du marché](docs/market_foundations.md)

## Problème

> Peut-on prévoir correctement les 24 prix horaires du lendemain tout en
> expliquant économiquement pourquoi le modèle anticipe un prix faible,
> élevé, négatif ou extrême ?

## Méthodologie

1. **Collecte** — prix (ENTSO-E), fondamentaux système (RTE), météo (Open-Meteo).
2. **Nettoyage** — fuseaux horaires, doublons, valeurs manquantes, unités.
3. **EDA marché** — merit order, residual load, prix négatifs, spikes, saisonnalité.
4. **Feature engineering** — lags, rolling stats, calendrier cyclique, interactions.
5. **Modèles** — baselines naïves (J-1/J-7) → régression/Ridge/Lasso → ARIMA/SARIMA → Random Forest/XGBoost.
6. **Validation** — split chronologique strict + walk-forward backtesting (expanding/rolling).
7. **Analyse des erreurs** — par heure, saison, régime de prix, residual load.

## Structure du repo

```
electricity-price-forecasting/
├── data/{raw,interim,processed}/   # non versionné (voir .gitignore)
├── notebooks/                       # 01 à 10, dans l'ordre du pipeline
├── src/                              # fonctions réutilisables (data, features, models, backtest, metrics, plots)
├── models/                           # modèles entraînés sérialisés
└── reports/figures/                  # graphiques exportés pour le rapport/portfolio
```

## Notebooks

| # | Notebook | Contenu |
|---|----------|---------|
| 01 | `price_data.ipynb` | Récupération des prix day-ahead via l'API ENTSO-E |
| 02 | `fundamentals.ipynb` | Demande, production par filière, échanges (RTE) |
| 03 | `cleaning.ipynb` | Fusion des sources, fuseaux horaires, cohérence temporelle |
| 04 | `market_eda.ipynb` | Distribution, saisonnalité, residual load, prix négatifs |
| 05 | `features.ipynb` | Pipeline de feature engineering |
| 06 | `baselines.ipynb` | Moyenne par heure, Naive J-1, Naive J-7 |
| 07 | `statistical_models.ipynb` | Régression linéaire, Ridge/Lasso, ARIMA/SARIMA |
| 08 | `ml_models.ipynb` | Random Forest, Gradient Boosting/XGBoost |
| 09 | `backtesting.ipynb` | Walk-forward backtest, comparaison des modèles |
| 10 | `error_analysis.ipynb` | Diagnostic par régime, heure, saison |

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # ou .venv\Scripts\activate sous Windows
pip install -r requirements.txt
```

Créer un fichier `.env` (non versionné) à la racine avec :

```
ENTSOE_API_KEY=xxxxxxxx
RTE_CLIENT_ID=xxxxxxxx
RTE_CLIENT_SECRET=xxxxxxxx
```

Le fichier `.env.example` peut être copié comme point de départ. Vérifier le
socle temporel avec `python -m unittest discover -s tests -v`.

- **Clé ENTSO-E** : compte gratuit sur https://transparency.entsoe.eu →
  paramètres du compte → "Web API Security Token".
- **Identifiants RTE** : compte développeur gratuit sur
  https://data.rte-france.com puis souscription aux APIs "Consumption",
  "Actual Generation", etc.
- **Open-Meteo** : aucune clé requise pour l'API archive historique.

## Data dictionary (V1)

| Colonne | Type | Rôle |
|---|---|---|
| `datetime` | timestamp | Index UTC ; conversion Europe/Paris pour l'analyse métier |
| `price_da` | float | Cible, €/MWh |
| `demand_forecast` | float | Fondamental |
| `wind_forecast` | float | Fondamental |
| `solar_forecast` | float | Fondamental |
| `nuclear_available` | float | Contrainte de capacité |
| `gas_price` | float | Coût marginal thermique |
| `co2_price` | float | Coût carbone |
| `temperature_forecast` | float | Driver de demande |
| `residual_load` | float | Demand − Wind − Solar |
| `price_da_lag_1d` / `price_da_lag_7d` | float | Mémoire J-1/J-7 robuste aux changements d'heure |
| `hour_sin` / `hour_cos` | float | Saisonnalité cyclique |

## Règle anti-leakage

Aucune variable utilisée pour prédire le jour D ne doit contenir d'information
indisponible au forecast origin. Les splits sont semi-ouverts. Les flags de
prix négatif et de spike sont réservés à l'analyse et le seuil de spike est
appris exclusivement sur le train.

## Statut

- ✅ Étape 0 — cadrage et contrat temporel.
- ✅ Étape 1 — fondamentaux du marché et hypothèses économiques.
- 🚧 Étape 2 — collecte et audit des prix, non commencée.
