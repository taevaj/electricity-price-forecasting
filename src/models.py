"""
models.py
---------
Baselines et modèles (section 10 du cahier de projet). Squelette à
implémenter progressivement aux notebooks 06 à 09.
"""

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------- #
# Niveau 0-1 : baselines naïves
# --------------------------------------------------------------------------- #
def naive_persistence(
    df: pd.DataFrame,
    price_col: str = "price_da",
    day_lag: int = 1,
    timezone: str = "Europe/Paris",
) -> pd.Series:
    """Baseline J-1/J-7 robuste aux journées locales de 23 ou 25 heures."""
    from src.features import add_price_day_lags

    column = f"{price_col}_lag_{day_lag}d"
    prediction = add_price_day_lags(
        df, price_col=price_col, day_lags=(day_lag,), timezone=timezone
    )[column]
    prediction.name = "y_pred"
    return prediction


def fit_mean_by_hour(
    train_df: pd.DataFrame,
    price_col: str = "price_da",
    hour_col: str = "hour",
) -> pd.Series:
    """Apprend les moyennes horaires exclusivement sur le train."""
    return train_df.groupby(hour_col)[price_col].mean()


def predict_mean_by_hour(
    df: pd.DataFrame,
    hourly_means: pd.Series,
    hour_col: str = "hour",
) -> pd.Series:
    """Applique des moyennes apprises sans consulter la cible de ``df``."""
    prediction = df[hour_col].map(hourly_means)
    if prediction.isna().any():
        missing = sorted(df.loc[prediction.isna(), hour_col].unique().tolist())
        raise ValueError(f"Heures absentes du train : {missing}")
    prediction.name = "y_pred"
    return prediction


# --------------------------------------------------------------------------- #
# Niveau 2 : régression linéaire / Ridge / Lasso
# --------------------------------------------------------------------------- #
def fit_linear_model(X_train, y_train, model_type: str = "ridge", alpha: float = 1.0):
    """
    model_type: "ols" | "ridge" | "lasso"
    Retourne le modèle sklearn entraîné.
    """
    from sklearn.linear_model import LinearRegression, Ridge, Lasso

    if model_type == "ols":
        model = LinearRegression()
    elif model_type == "ridge":
        model = Ridge(alpha=alpha)
    elif model_type == "lasso":
        model = Lasso(alpha=alpha)
    else:
        raise ValueError(f"model_type inconnu : {model_type}")

    model.fit(X_train, y_train)
    return model


# --------------------------------------------------------------------------- #
# Niveau 3 : ARIMA / SARIMA
# --------------------------------------------------------------------------- #
def fit_sarima(y_train, order=(1, 1, 1), seasonal_order=(1, 1, 1, 24)):
    """Nécessite statsmodels. À utiliser comme benchmark série temporelle pur."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    model = SARIMAX(y_train, order=order, seasonal_order=seasonal_order,
                     enforce_stationarity=False, enforce_invertibility=False)
    return model.fit(disp=False)


# --------------------------------------------------------------------------- #
# Niveau 4 : Random Forest / Gradient Boosting
# --------------------------------------------------------------------------- #
def fit_random_forest(X_train, y_train, **kwargs):
    from sklearn.ensemble import RandomForestRegressor

    defaults = dict(n_estimators=500, max_depth=None, n_jobs=-1, random_state=42)
    defaults.update(kwargs)
    model = RandomForestRegressor(**defaults)
    model.fit(X_train, y_train)
    return model


def fit_xgboost(X_train, y_train, **kwargs):
    from xgboost import XGBRegressor

    defaults = dict(n_estimators=800, max_depth=6, learning_rate=0.03,
                     subsample=0.8, colsample_bytree=0.8, random_state=42)
    defaults.update(kwargs)
    model = XGBRegressor(**defaults)
    model.fit(X_train, y_train)
    return model


# --------------------------------------------------------------------------- #
# Niveau 5 : régression quantile / conformal (extension V2)
# --------------------------------------------------------------------------- #
def fit_quantile_gbm(X_train, y_train, quantile: float = 0.5, **kwargs):
    """GradientBoostingRegressor en mode pinball loss pour un quantile donné."""
    from sklearn.ensemble import GradientBoostingRegressor

    defaults = dict(loss="quantile", alpha=quantile, n_estimators=500,
                     max_depth=3, learning_rate=0.03, random_state=42)
    defaults.update(kwargs)
    model = GradientBoostingRegressor(**defaults)
    model.fit(X_train, y_train)
    return model
