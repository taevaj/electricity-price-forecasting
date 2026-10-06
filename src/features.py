"""Feature engineering temporel pour le forecast day-ahead français."""

import numpy as np
import pandas as pd


def _local_delivery_keys(index: pd.DatetimeIndex, timezone: str) -> pd.DataFrame:
    """Construit des clés locales stables, y compris pour l'heure DST répétée."""
    if not isinstance(index, pd.DatetimeIndex) or index.tz is None:
        raise TypeError("Le pipeline day-ahead exige un DatetimeIndex timezone-aware")
    local = index.tz_convert(timezone)
    folds = np.fromiter((timestamp.fold for timestamp in local), dtype=int, count=len(local))
    return pd.DataFrame(
        {"delivery_date": local.date, "delivery_period": local.hour * 2 + folds},
        index=index,
    )


def add_price_lags(
    df: pd.DataFrame,
    price_col: str = "price_da",
    lags=(48, 168),
    min_lag_hours: int = 25,
) -> pd.DataFrame:
    """Ajoute des lags absolus ; le pipeline principal préfère les day lags."""
    out = df.copy()
    for lag in lags:
        if lag < min_lag_hours:
            raise ValueError(f"Lag {lag} h interdit : minimum absolu {min_lag_hours} h")
        out[f"{price_col}_lag_{lag}"] = out[price_col].shift(lag)
    return out


def add_price_day_lags(
    df: pd.DataFrame,
    price_col: str = "price_da",
    day_lags=(1, 2, 7),
    timezone: str = "Europe/Paris",
) -> pd.DataFrame:
    """Ajoute J-1/J-2/J-7 sans supposer qu'un jour contient 24 périodes."""
    if any(day < 1 for day in day_lags):
        raise ValueError("Tous les day_lags doivent être supérieurs ou égaux à 1")
    out = df.copy()
    keys = _local_delivery_keys(out.index, timezone)
    lookup = pd.Series(
        out[price_col].to_numpy(),
        index=pd.MultiIndex.from_arrays(
            [keys["delivery_date"], keys["delivery_period"]],
            names=["delivery_date", "delivery_period"],
        ),
    )
    local_dates = pd.to_datetime(keys["delivery_date"])
    periods = keys["delivery_period"].to_numpy()
    for day in day_lags:
        prior_dates = (local_dates - pd.DateOffset(days=day)).dt.date
        prior_keys = pd.MultiIndex.from_arrays([prior_dates, periods])
        out[f"{price_col}_lag_{day}d"] = lookup.reindex(prior_keys).to_numpy()
    return out


def add_rolling_stats(
    df: pd.DataFrame,
    col: str,
    windows=(24, 168),
    availability_lag_hours: int = 25,
) -> pd.DataFrame:
    """Ajoute des rolling absolus avec un recul sûr même lors d'un jour de 25 h."""
    if availability_lag_hours < 25:
        raise ValueError("Le décalage absolu doit être d'au moins 25 h en day-ahead")
    out = df.copy()
    shifted = out[col].shift(availability_lag_hours)
    for window in windows:
        out[f"{col}_rollmean_{window}"] = shifted.rolling(window).mean()
        out[f"{col}_rollstd_{window}"] = shifted.rolling(window).std()
    return out


def add_price_daily_rolling_stats(
    df: pd.DataFrame,
    price_col: str = "price_da",
    windows_days=(1, 7),
    timezone: str = "Europe/Paris",
) -> pd.DataFrame:
    """Calcule mean/std sur les jours locaux strictement antérieurs à D."""
    out = df.copy()
    keys = _local_delivery_keys(out.index, timezone)
    work = pd.DataFrame(
        {"delivery_date": pd.to_datetime(keys["delivery_date"]), price_col: out[price_col].to_numpy()}
    )
    work["square"] = work[price_col] ** 2
    daily = work.groupby("delivery_date").agg(
        value_sum=(price_col, "sum"), value_count=(price_col, "count"), square_sum=("square", "sum")
    )
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="D"), fill_value=0)
    row_dates = pd.to_datetime(keys["delivery_date"])
    for window in windows_days:
        if window < 1:
            raise ValueError("Les fenêtres journalières doivent être positives")
        previous = daily.shift(1).rolling(window, min_periods=window).sum()
        mean = previous["value_sum"] / previous["value_count"]
        numerator = previous["square_sum"] - previous["value_sum"] ** 2 / previous["value_count"]
        std = np.sqrt(numerator.clip(lower=0) / (previous["value_count"] - 1))
        out[f"{price_col}_rollmean_{window}d"] = row_dates.map(mean).to_numpy()
        out[f"{price_col}_rollstd_{window}d"] = row_dates.map(std).to_numpy()
    return out


def add_calendar_features(
    df: pd.DataFrame, datetime_col: str = None, timezone: str = "Europe/Paris"
) -> pd.DataFrame:
    """Ajoute calendrier et encodages cycliques dans le fuseau métier."""
    out = df.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out[datetime_col])) if datetime_col else out.index
    if not isinstance(idx, pd.DatetimeIndex):
        raise TypeError("Un DatetimeIndex ou une colonne datetime valide est requis")
    if idx.tz is not None:
        idx = idx.tz_convert(timezone)
    out["hour"] = idx.hour
    out["weekday"] = idx.dayofweek
    out["is_weekend"] = (idx.dayofweek >= 5).astype(int)
    out["month"] = idx.month
    out["hour_sin"] = np.sin(2 * np.pi * out["hour"] / 24)
    out["hour_cos"] = np.cos(2 * np.pi * out["hour"] / 24)
    out["weekday_sin"] = np.sin(2 * np.pi * out["weekday"] / 7)
    out["weekday_cos"] = np.cos(2 * np.pi * out["weekday"] / 7)
    return out


def add_residual_load(
    df: pd.DataFrame,
    demand_col="demand_forecast",
    wind_col="wind_forecast",
    solar_col="solar_forecast",
) -> pd.DataFrame:
    """Residual Load = Demand - Wind - Solar."""
    out = df.copy()
    out["residual_load"] = out[demand_col] - out[wind_col] - out[solar_col]
    return out


def fit_spike_threshold(
    train_df: pd.DataFrame, price_col: str = "price_da", spike_quantile: float = 0.95
) -> float:
    """Estime le seuil de spike sur le train uniquement."""
    if not 0 < spike_quantile < 1:
        raise ValueError("spike_quantile doit être strictement compris entre 0 et 1")
    return float(train_df[price_col].quantile(spike_quantile))


def add_regime_flags(
    df: pd.DataFrame, spike_threshold: float, price_col: str = "price_da"
) -> pd.DataFrame:
    """Ajoute des étiquettes d'analyse, jamais des features prédictives."""
    out = df.copy()
    out["negative_price_flag"] = (out[price_col] < 0).astype(int)
    out["spike_flag"] = (out[price_col] >= spike_threshold).astype(int)
    return out


def build_feature_pipeline(df: pd.DataFrame) -> pd.DataFrame:
    """Construit uniquement les features admissibles au modèle day-ahead."""
    out = add_residual_load(df)
    out = add_price_day_lags(out)
    out = add_price_daily_rolling_stats(out)
    out = add_calendar_features(out)
    return out
