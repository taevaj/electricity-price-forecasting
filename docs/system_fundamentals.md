# Collecte des fondamentaux du système électrique

## Objectif

Cette note documente l'étape 3 du projet : collecter et préparer les fondamentaux du système électrique français sur la même grille horaire que les prix day-ahead. Elle couvre la demande, la prévision de demande J-1, la production par filière et le solde des échanges physiques.

La disponibilité nucléaire et les prix de marché du gaz et du CO₂ ne sont pas encore collectés. Ils restent explicitement séparés des variables observées afin de ne pas créer de variables trompeuses.

## 1. Source

Les données proviennent du jeu public **Données éCO2mix nationales consolidées et définitives** de RTE, diffusé par Open Data Réseaux Énergies.

| Élément | Valeur |
|---|---|
| Producteur | RTE |
| Portail | Open Data Réseaux Énergies, ODRÉ |
| Identifiant | `eco2mix-national-cons-def` |
| Accès | API Explore publique, sans identifiant |
| Zone | France |
| Période retenue | 1er janvier 2022 au 30 septembre 2025 inclus |
| Index final | UTC |
| Fréquence finale | Horaire |

Le jeu consolidé contient notamment la consommation réalisée, les prévisions de consommation J-1 et J, la production par filière et les échanges physiques. La prévision J-1 est publiée au quart d'heure ; les variables réalisées sont principalement disponibles à la demi-heure.

## 2. Extraction

L'extraction sélectionne les 13 champs suivants :

```text
date_heure
consommation
prevision_j1
fioul
charbon
gaz
nucleaire
eolien
solaire
hydraulique
pompage
bioenergies
ech_physiques
```

La réponse brute contient 131 620 lignes et 13 colonnes. Les timestamps sont demandés en UTC, convertis avec `pandas`, triés, puis utilisés comme index.

## 3. Passage à la fréquence horaire

Les séries sources mélangent des pas de 15 et 30 minutes. Comme les valeurs représentent des puissances en MW, le passage à l'heure utilise la moyenne des valeurs infra-horaires :

```python
eco2mix_hourly = eco2mix_raw.resample("h").mean()
```

Le résultat est ensuite réindexé sur l'index des prix :

```python
eco2mix_hourly = eco2mix_hourly.reindex(price_index)
```

Cette opération garantit une correspondance exacte avec les 32 855 périodes de livraison de la cible.

## 4. Variables collectées

### Demande

| Colonne source | Nom analytique | Unité | Statut anti-leakage |
|---|---|---|---|
| `consommation` | `demand_actual` | MW | `diagnostic_only` |
| `prevision_j1` | `demand_forecast_j1` | MW | Candidat, heure de publication à vérifier |

La consommation réalisée décrit correctement le système, mais elle n'est pas connue au forecast origin. Elle ne doit donc pas être utilisée directement dans un backtest day-ahead opérationnel.

La prévision J-1 est plus proche du besoin opérationnel. Son utilisation comme feature reste conditionnée à la vérification de son heure exacte de publication et à la règle `available_at_utc <= forecast_origin_utc`.

### Production observée

| Colonne source | Nom analytique | Unité | Statut anti-leakage |
|---|---|---|---|
| `nucleaire` | `nuclear_generation` | MW | `diagnostic_only` |
| `eolien` | `wind_generation` | MW | `diagnostic_only` |
| `solaire` | `solar_generation` | MW | `diagnostic_only` |
| `hydraulique` | `hydro_generation` | MW | `diagnostic_only` |
| `gaz` | `gas_generation` | MW | `diagnostic_only` |
| `charbon` | `coal_generation` | MW | `diagnostic_only` |
| `fioul` | `oil_generation` | MW | `diagnostic_only` |
| `bioenergies` | `bioenergy_generation` | MW | `diagnostic_only` |
| `pompage` | `pumping_consumption` | MW | `diagnostic_only` |

Ces colonnes sont des productions réalisées. Pour un modèle opérationnel, l'éolien et le solaire devront être remplacés par les prévisions disponibles avant l'enchère. La production nucléaire observée ne mesure pas la capacité nucléaire disponible.

### Échanges physiques

| Colonne source | Nom analytique | Unité | Convention |
|---|---|---|---|
| `ech_physiques` | `net_import_mw` | MW | Positif : import net ; négatif : export net |

Les échanges physiques réalisés sont utiles pour expliquer les régimes de marché, mais ne sont pas connus à l'avance. Une V1 opérationnelle devra utiliser une information disponible avant l'enchère, par exemple des capacités, nominations ou prévisions correctement horodatées.

## 5. Trois heures manquantes

Après l'alignement sur les prix, trois lignes sont entièrement manquantes :

```text
2022-10-30 00:00:00+00:00
2023-10-29 00:00:00+00:00
2024-10-27 00:00:00+00:00
```

Ces trois timestamps correspondent aux passages européens à l'heure d'hiver. Chaque journée concernée comporte deux périodes locales portant l'heure `02:00`, mais représentant deux heures UTC différentes.

Afin de conserver une grille UTC continue et une correspondance exacte avec les prix, les trois lignes sont interpolées temporellement. Une colonne de traçabilité est conservée :

```python
eco2mix_hourly["data_imputed"] = (
    eco2mix_hourly.isna().any(axis=1).astype("int8")
)

eco2mix_hourly[numeric_columns] = (
    eco2mix_hourly[numeric_columns]
    .interpolate(method="time", limit=3, limit_area="inside")
)
```

`data_imputed = 1` identifie les trois heures corrigées. L'interpolation porte sur trois heures parmi 32 855 et doit être conservée dans les analyses de sensibilité.

## 6. Fichier produit

```text
data/raw/rte_eco2mix_hourly_fr.csv
```

Le fichier final contient :

| Contrôle | Résultat |
|---|---:|
| Lignes | 32 855 |
| Variables énergétiques | 12 |
| Colonne de qualité | `data_imputed` |
| Index identique aux prix | Oui |
| Timestamps dupliqués | 0 |
| Valeurs manquantes après correction | 0 |
| Heures interpolées | 3 |

## 7. Variables encore absentes

### Disponibilité nucléaire

La production nucléaire observée n'est pas une mesure de disponibilité. Une centrale peut être disponible sans produire à pleine puissance. Une source dédiée aux indisponibilités ou à la capacité disponible doit donc être collectée séparément, avec son heure de publication.

### Prix du gaz

La colonne `gaz` d'éCO2mix mesure la production électrique issue du gaz en MW. Elle ne représente pas un prix de marché. Le driver économique recherché est une série de prix du gaz, par exemple un produit TTF documenté et correctement daté.

### Prix du CO₂

Le driver CO₂ recherché correspond au prix des quotas EU ETS, généralement représenté par un contrat EUA. Il nécessite également une source de marché distincte.

Les séries gaz et CO₂ devront respecter les calendriers de marché, les jours sans cotation et la règle du dernier prix disponible avant le forecast origin. Aucun remplissage utilisant une cotation future ne sera autorisé.

## 8. Contrat anti-leakage

| Variable | Usage actuel | Usage opérationnel futur |
|---|---|---|
| Consommation réalisée | EDA et diagnostic | Remplacer par forecast admissible |
| Prévision de demande J-1 | Candidat | Vérifier `available_at_utc` |
| Production réalisée | EDA et diagnostic | Remplacer par forecasts pré-enchère |
| Échanges physiques réalisés | EDA et diagnostic | Remplacer par information pré-enchère |
| Disponibilité nucléaire | Non collectée | Collecter avec publication historique |
| Gaz et CO₂ | Non collectés | Dernière cotation connue au forecast origin |

Les fondamentaux réalisés ne doivent pas être utilisés comme features contemporaines dans un backtest présenté comme opérationnel. Ils restent cependant utiles pour comprendre les prix négatifs, les spikes et les régimes de tension.

## 9. Statut de l'étape 3

| Composante | Statut |
|---|---|
| Demande réalisée | Collectée et contrôlée |
| Prévision de demande J-1 | Collectée ; disponibilité à vérifier |
| Production par filière | Collectée et contrôlée |
| Échanges physiques | Collectés et contrôlés |
| Disponibilité nucléaire | À collecter |
| Prix du gaz TTF | À collecter |
| Prix des quotas CO₂ EUA | À collecter |

Le cœur éCO2mix de l'étape 3 est terminé. L'étape complète reste partiellement ouverte jusqu'à l'ajout ou à l'abandon documenté de la disponibilité nucléaire, du gaz et du CO₂.

## Sources officielles

- [ODRÉ — Données éCO2mix nationales consolidées et définitives](https://odre.opendatasoft.com/explore/dataset/eco2mix-national-cons-def/)
- [RTE — éCO2mix](https://www.rte-france.com/eco2mix)
- [OpenDataSoft — Explore API v2.1](https://help.opendatasoft.com/apis/ods-explore-v2/)

Sources consultées le 18 septembre 2026.
