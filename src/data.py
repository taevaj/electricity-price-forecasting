"""
data.py
-------
Fonctions de collecte de données pour le projet Electricity Price Forecasting
(France, day-ahead).

Sources couvertes :
    1. ENTSO-E Transparency Platform -> prix day-ahead (via la librairie entsoe-py)
    2. RTE APIs (data.rte-france.com) -> fondamentaux système (conso, prod, échanges)
    3. Open-Meteo -> météo historique (température, vent, irradiance)

Toutes les fonctions retournent des pandas DataFrame/Series indexés en UTC.
Europe/Paris est réservé aux dates et heures métier.

IMPORTANT (règle d'or anti-leakage, section 5 du cahier de projet) :
Ces fonctions récupèrent des OBSERVATIONS HISTORIQUES (niveau A/B de qualité,
section 8.3). Pour un backtest réellement opérationnel (niveau C), il faudra
remplacer les séries "réalisées" (conso réelle, vent réel...) par les
FORECASTS qui étaient disponibles avant la fermeture du marché day-ahead,
et aligner chaque donnée sur son timestamp de publication réel.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Optional

import pandas as pd

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
# Toutes les clés/secrets sont lus depuis les variables d'environnement.
# Ne jamais committer de clé API en dur dans le code -> utiliser un fichier
# .env (non versionné, cf. .gitignore) chargé avec python-dotenv.
#
#   ENTSOE_API_KEY=xxxx
#   RTE_CLIENT_ID=xxxx
#   RTE_CLIENT_SECRET=xxxx

ENTSOE_API_KEY = os.environ.get("ENTSOE_API_KEY")
RTE_CLIENT_ID = os.environ.get("RTE_CLIENT_ID")
RTE_CLIENT_SECRET = os.environ.get("RTE_CLIENT_SECRET")

PARIS_TZ = "Europe/Paris"
UTC_TZ = "UTC"


# --------------------------------------------------------------------------- #
# 1) ENTSO-E Transparency Platform — prix day-ahead
# --------------------------------------------------------------------------- #
def fetch_entsoe_day_ahead_prices(
    start: str,
    end: str,
    country_code: str = "FR",
    api_key: Optional[str] = None,
) -> pd.Series:
    """
    Récupère les prix day-ahead horaires depuis ENTSO-E Transparency Platform.

    Nécessite le package `entsoe-py` (pip install entsoe-py) et une clé API
    ENTSO-E (demande gratuite via un compte sur transparency.entsoe.eu,
    section "Web API Security Token" dans les paramètres du compte).

    Parameters
    ----------
    start, end : str
        Dates au format "YYYY-MM-DD".
    country_code : str
        Zone de dépôt des offres. "FR" pour la France.
    api_key : str, optional
        Si None, utilise la variable d'environnement ENTSOE_API_KEY.

    Returns
    -------
    pd.Series
        Index = timestamp horaire UTC, valeurs = prix en €/MWh.
    """
    from entsoe import EntsoePandasClient  # import local pour ne pas forcer la dépendance

    key = api_key or ENTSOE_API_KEY
    if not key:
        raise ValueError(
            "Clé API ENTSO-E manquante. Définis la variable d'environnement "
            "ENTSOE_API_KEY ou passe api_key=... explicitement."
        )

    client = EntsoePandasClient(api_key=key)

    start_ts = pd.Timestamp(start, tz=PARIS_TZ)
    end_ts = pd.Timestamp(end, tz=PARIS_TZ)

    prices = client.query_day_ahead_prices(country_code, start=start_ts, end=end_ts)
    prices.index = prices.index.tz_convert(UTC_TZ)
    prices.name = "price_da"
    prices.index.name = "datetime"
    return prices


def fetch_entsoe_load_and_generation(
    start: str,
    end: str,
    country_code: str = "FR",
    api_key: Optional[str] = None,
) -> pd.DataFrame:
    """
    Récupère en complément la demande réalisée et le mix de production par
    filière depuis ENTSO-E (utile si tu préfères une seule source aux
    fondamentaux plutôt que de mélanger ENTSO-E et RTE).

    Returns
    -------
    pd.DataFrame avec (au moins) les colonnes : load, et une colonne par
    filière de production disponible (ex. "Nuclear", "Wind Onshore",
    "Solar", "Hydro Run-of-river and poundage", ...).
    """
    from entsoe import EntsoePandasClient

    key = api_key or ENTSOE_API_KEY
    if not key:
        raise ValueError("Clé API ENTSO-E manquante (ENTSOE_API_KEY).")

    client = EntsoePandasClient(api_key=key)
    start_ts = pd.Timestamp(start, tz=PARIS_TZ)
    end_ts = pd.Timestamp(end, tz=PARIS_TZ)

    load = client.query_load(country_code, start=start_ts, end=end_ts)
    generation = client.query_generation(country_code, start=start_ts, end=end_ts)

    load = load.rename(columns={load.columns[0]: "load"}) if hasattr(load, "columns") else load.to_frame("load")
    df = generation.join(load, how="outer")
    df.index = df.index.tz_convert(UTC_TZ)
    df.index.name = "datetime"
    return df


# --------------------------------------------------------------------------- #
# 2) RTE APIs (data.rte-france.com) — fondamentaux système français
# --------------------------------------------------------------------------- #
def get_rte_access_token(client_id: Optional[str] = None, client_secret: Optional[str] = None) -> str:
    """
    Authentification OAuth2 (client_credentials) auprès de RTE.

    Un compte développeur gratuit est nécessaire sur https://data.rte-france.com
    puis la souscription aux APIs souhaitées (ex. "Consumption", "Generation
    Forecast", "Physical Flows", "Actual Generation").

    Returns
    -------
    str : access_token à utiliser dans le header Authorization des appels suivants.
    """
    import requests
    cid = client_id or RTE_CLIENT_ID
    secret = client_secret or RTE_CLIENT_SECRET
    if not cid or not secret:
        raise ValueError(
            "Identifiants RTE manquants. Définis RTE_CLIENT_ID et RTE_CLIENT_SECRET."
        )

    token_url = "https://digital.iservices.rte-france.com/token/oauth/"
    credentials = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    headers = {"Authorization": f"Basic {credentials}"}

    resp = requests.post(token_url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_rte_actual_generation(
    start: str,
    end: str,
    token: Optional[str] = None,
    production_type: Optional[str] = None,
) -> pd.DataFrame:
    """
    Récupère la production réalisée par filière via l'API RTE
    "Actual Generation" (endpoint /actual_generation/v1/actual_generations_per_production_type).

    Parameters
    ----------
    start, end : str
        Dates ISO 8601, ex. "2023-01-01T00:00:00+01:00".
    token : str, optional
        Access token RTE. Si None, en génère un automatiquement.
    production_type : str, optional
        Filtrer sur une filière donnée (ex. "NUCLEAR", "WIND", "SOLAR").
        Si None, retourne toutes les filières disponibles.

    Returns
    -------
    pd.DataFrame long format : datetime, production_type, value (MW).
    Utiliser `.pivot(index="datetime", columns="production_type", values="value")`
    pour obtenir un format large exploitable dans le merge du notebook 03.
    """
    import requests
    access_token = token or get_rte_access_token()
    url = "https://digital.iservices.rte-france.com/open_api/actual_generation/v1/actual_generations_per_production_type"

    params = {"start_date": start, "end_date": end}
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    rows = []
    for series in payload.get("actual_generations_per_production_type", []):
        p_type = series["production_type"]
        if production_type and p_type != production_type:
            continue
        for point in series["values"]:
            rows.append({
                "datetime": point["start_date"],
                "production_type": p_type,
                "value": point["value"],
            })

    df = pd.DataFrame(rows)
    if not df.empty:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    return df


def fetch_rte_consumption(start: str, end: str, token: Optional[str] = None) -> pd.DataFrame:
    """
    Récupère la consommation réalisée (short-term) via l'API RTE "Consumption".
    Endpoint : /consumption/v1/short_term

    Returns
    -------
    pd.DataFrame : datetime (index), demand (MW).
    """
    import requests
    access_token = token or get_rte_access_token()
    url = "https://digital.iservices.rte-france.com/open_api/consumption/v1/short_term"
    params = {"start_date": start, "end_date": end}
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = requests.get(url, headers=headers, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    rows = []
    for series in payload.get("short_term", []):
        for point in series.get("values", []):
            rows.append({"datetime": point["start_date"], "demand": point["value"]})

    df = pd.DataFrame(rows)
    if not df.empty:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df = df.set_index("datetime").sort_index()
    return df


# --------------------------------------------------------------------------- #
# 3) Open-Meteo — météo historique (gratuit, sans clé API)
# --------------------------------------------------------------------------- #
def fetch_openmeteo_weather(
    start: str,
    end: str,
    latitude: float = 48.85,
    longitude: float = 2.35,
    variables: tuple = ("temperature_2m", "wind_speed_10m", "shortwave_radiation"),
) -> pd.DataFrame:
    """
    Récupère la météo historique horaire via l'API Open-Meteo Archive
    (aucune clé requise). Par défaut sur Paris ; à adapter ou multiplier sur
    plusieurs points (ex. moyenne pondérée par la population/consommation
    régionale) pour une meilleure représentativité nationale.

    Documentation : https://open-meteo.com/en/docs/historical-weather-api

    Parameters
    ----------
    start, end : str
        Dates au format "YYYY-MM-DD".
    latitude, longitude : float
        Coordonnées du point météo.
    variables : tuple[str]
        Variables horaires demandées.

    Returns
    -------
        pd.DataFrame indexé par datetime UTC, une colonne par variable.
    """
    import requests
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start,
        "end_date": end,
        "hourly": ",".join(variables),
        "timezone": UTC_TZ,
    }

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    df = pd.DataFrame(payload["hourly"])
    df["datetime"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop(columns=["time"]).set_index("datetime").sort_index()
    return df


def fetch_openmeteo_forecast_archive(
    start: str,
    end: str,
    latitude: float = 48.85,
    longitude: float = 2.35,
) -> pd.DataFrame:
    """
    NOTE (anti-leakage, section 4.2 / niveau C section 8.3) :
    `fetch_openmeteo_weather` renvoie des OBSERVATIONS, utiles pour l'analyse
    exploratoire (niveau A) mais pas pour un backtest opérationnel réaliste,
    puisqu'elles ne seraient pas connues avant la fermeture du marché
    day-ahead. Pour un pipeline niveau C, il faut utiliser les prévisions
    météo historiques (Open-Meteo propose une "Previous Runs API" /
    forecast archive) alignées sur l'heure réelle d'émission de la
    prévision J-1. Ce stub documente l'intention ; à implémenter au moment
    de construire le benchmark opérationnel de la V1.
    """
    raise NotImplementedError(
        "À implémenter avec l'API de prévisions archivées d'Open-Meteo "
        "(ou un autre fournisseur) une fois la V1 (niveau A/B) validée."
    )


# --------------------------------------------------------------------------- #
# Utilitaires génériques
# --------------------------------------------------------------------------- #
def save_raw(df, name: str, raw_dir: str = "../data/raw", overwrite: bool = False) -> str:
    """Sauvegarde un export brut sans écrasement silencieux."""
    os.makedirs(raw_dir, exist_ok=True)
    path = os.path.join(raw_dir, f"{name}.csv")
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(f"Le fichier raw existe déjà : {path}")
    df.to_csv(path)
    return path


def polite_sleep(seconds: float = 1.0) -> None:
    """Petite pause entre appels API successifs pour respecter les rate limits."""
    time.sleep(seconds)
