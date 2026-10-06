# Collecte des prix et de la météo

## Objectif

Cette note documente l'étape 2 du projet : constituer une cible horaire de prix day-ahead français et préparer une première source météo historique pour l'analyse exploratoire. La période métier couvre le 1er janvier 2022 au 30 septembre 2025 inclus.

## 1. Périmètre temporel

| Élément | Valeur |
|---|---|
| Zone de marché | France, `BZN|FR` |
| Début métier | 1er janvier 2022 à 00:00 Europe/Paris |
| Fin métier | 30 septembre 2025 à 23:00 Europe/Paris |
| Index de calcul | UTC |
| Fréquence finale | Horaire |
| Nombre attendu d'heures | 32 855 |

Les bornes UTC équivalentes vont du 31 décembre 2021 à 23:00 UTC au 30 septembre 2025 à 21:00 UTC. Le nombre d'heures ne correspond pas simplement au nombre de jours multiplié par 24, car la période traverse les changements d'heure européens.

## 2. Prix day-ahead ENTSO-E

### Source

Les prix proviennent de l'ENTSO-E Transparency Platform, vue **Market — Energy Prices**, pour la bidding zone française. En l'absence de jeton API, les exports officiels de l'interface graphique ont été téléchargés par année puis fusionnés.

Fichiers sources utilisés :

```text
GUI_ENERGY_PRICES_202112312300-202212312300.csv
GUI_ENERGY_PRICES_202212312300-202312312300.csv
GUI_ENERGY_PRICES_202312312300-202412312300.csv
GUI_ENERGY_PRICES_202412312300-202512312300.csv
```

Le dernier export contient toute l'année 2025, mais seules les observations antérieures au 1er octobre 2025 sont retenues.

### Traitements

1. Vérification de la zone `BZN|FR` et de la présence du prix day-ahead.
2. Lecture des intervalles `MTU (CET/CEST)`.
3. Désambiguïsation explicite des passages CET/CEST.
4. Conversion du début de chaque intervalle en UTC.
5. Filtrage sur la période métier définie dans la spécification V1.
6. Réduction à une observation par heure.
7. Tri chronologique et renommage de la cible en `price_da`.

L'export 2025 est présenté par quarts d'heure. Jusqu'au 30 septembre 2025 inclus, les quatre quarts d'heure d'une même heure portent le même prix. Ils sont donc regroupés sans approximation en une seule observation horaire. Les données postérieures, où les prix infra-horaires peuvent différer, sont exclues de la V1.

### Fichier produit

```text
data/raw/entsoe_day_ahead_prices_fr.csv
```

| Colonne | Type | Unité | Description |
|---|---|---|---|
| `datetime` | timestamp UTC | heure | Début de la période de livraison |
| `price_da` | float | EUR/MWh | Prix day-ahead de la zone française |

### Contrôles obtenus

| Contrôle | Résultat |
|---|---:|
| Observations | 32 855 |
| Timestamps dupliqués | 0 |
| Heures manquantes | 0 |
| Prix manquants | 0 |
| Pas temporel non horaire | 0 |
| Prix négatifs | 996 |
| Minimum | -134,94 EUR/MWh |
| Maximum | 2 987,78 EUR/MWh |

Les prix négatifs et les valeurs extrêmes sont conservés. Ils représentent des régimes de marché à analyser, pas des erreurs à supprimer automatiquement.

## 3. Météo historique Open-Meteo

### Source

La météo provient de l'API historique Open-Meteo pour un point situé à Paris :

```text
latitude = 48.85
longitude = 2.35
```

Variables récupérées :

| Colonne | Unité finale | Rôle exploratoire |
|---|---|---|
| `temperature_2m` | °C | Proxy des besoins de chauffage et de climatisation |
| `wind_speed_10m` | m/s | Proxy météorologique de la production éolienne |
| `shortwave_radiation` | W/m² | Proxy météorologique de la production solaire |

Open-Meteo renvoie par défaut le vent en km/h. La variable `wind_speed_10m` est divisée par 3,6 avant sa sauvegarde afin de correspondre à l'unité m/s annoncée dans le notebook.

### Alignement

La requête brute sur les dates calendaires renvoie 32 856 lignes en UTC. Pour éviter un décalage aux bornes et garantir une jointure exacte, la série météo est réindexée directement sur l'index des prix :

```python
weather = weather.reindex(prices.index)
```

Après alignement, le résultat attendu est de 32 855 lignes, avec un index strictement identique à celui de `prices` et aucune valeur manquante.

### Fichier produit

```text
data/raw/openmeteo_weather_paris.csv
```

Le fichier peut être régénéré avec :

```python
save_raw(
    weather,
    "openmeteo_weather_paris",
    raw_dir="../data/raw",
    overwrite=True,
)
```

## 4. Contrôles de validation

Les deux séries sont prêtes pour l'étape de nettoyage lorsque les assertions suivantes passent :

```python
assert prices.index.equals(weather.index)
assert prices.index.tz is not None
assert str(prices.index.tz) == "UTC"
assert prices.index.duplicated().sum() == 0
assert weather.index.duplicated().sum() == 0
assert prices.isna().sum() == 0
assert weather.isna().sum().sum() == 0
assert len(prices) == len(weather) == 32855
```

## 5. Contrat anti-leakage

Le prix day-ahead est la cible à prévoir. Il ne doit jamais apparaître dans les variables explicatives contemporaines ou futures. Seuls ses lags réellement disponibles au forecast origin pourront devenir des features.

La météo collectée ici est une **observation historique réalisée**. Elle est adaptée à l'EDA et à un benchmark explicatif de niveau A/B, mais elle n'était pas connue au moment de la prévision day-ahead. Elle est donc marquée `diagnostic_only` pour l'instant. Un backtest opérationnel de niveau C devra utiliser des prévisions météo archivées, associées à leur heure réelle de publication.

## 6. Limites

- Paris seul ne représente pas toute la météo française.
- La vitesse du vent à 10 mètres n'est pas une prévision directe de production éolienne.
- L'irradiance parisienne n'est pas une prévision nationale de production solaire.
- Les exports manuels ENTSO-E sont reproductibles, mais moins automatisés qu'un accès API.
- Les données brutes sont exclues de Git par `.gitignore` ; leur provenance et leurs transformations doivent donc rester documentées.
- La V1 s'arrête avant le passage opérationnel aux prix day-ahead infra-horaires d'octobre 2025.

## 7. Validation de l'étape 2

L'étape est validée lorsque :

1. le fichier de prix contient exactement 32 855 heures continues en UTC ;
2. les prix négatifs et les spikes sont conservés ;
3. le fichier météo possède le même index que les prix ;
4. l'unité du vent est explicitement convertie en m/s ;
5. la météo réalisée est identifiée comme donnée de diagnostic afin d'éviter le data leakage.

La prochaine étape consiste à collecter les fondamentaux du système électrique : demande, production par filière, disponibilité nucléaire et échanges transfrontaliers.

## Sources officielles

- [ENTSO-E Transparency Platform — Energy Prices](https://transparency.entsoe.eu/market/energyPrices)
- [Open-Meteo — Historical Weather API](https://open-meteo.com/en/docs/historical-weather-api)

Sources consultées le 17 septembre 2026.
