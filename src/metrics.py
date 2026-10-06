"""
metrics.py
----------
Métriques d'évaluation pour le forecasting de prix day-ahead.

Toutes les fonctions acceptent des array-like (numpy, pandas Series) de même
longueur : y_true (valeurs réelles) et y_pred (valeurs prédites).
"""

import numpy as np
import pandas as pd


def mae(y_true, y_pred) -> float:
    """Mean Absolute Error (€/MWh)."""
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred) -> float:
    """Root Mean Squared Error (€/MWh)."""
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def smape(y_true, y_pred, epsilon: float = 1e-3) -> float:
    """
    Symmetric MAPE (%). À utiliser avec prudence quand les prix sont proches
    de zéro ou négatifs (cf. section 12 du cahier de projet) : préférer
    MAE/RMSE comme métriques principales.
    """
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    denom = np.abs(y_true) + np.abs(y_pred) + epsilon
    return float(100 * np.mean(2 * np.abs(y_true - y_pred) / denom))


def bias(y_true, y_pred) -> float:
    """Biais moyen (positif = le modèle sous-estime en moyenne)."""
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    return float(np.mean(y_true - y_pred))


def summary_metrics(y_true, y_pred) -> dict:
    """Retourne un dict avec toutes les métriques principales."""
    return {
        "MAE": mae(y_true, y_pred),
        "RMSE": rmse(y_true, y_pred),
        "sMAPE": smape(y_true, y_pred),
        "Bias": bias(y_true, y_pred),
        "n_obs": len(np.asarray(y_true)),
    }


def metrics_by_group(df: pd.DataFrame, y_true_col: str, y_pred_col: str, group_col: str) -> pd.DataFrame:
    """
    Calcule MAE/RMSE/sMAPE par groupe (heure, saison, régime de prix, etc.).

    Exemple :
        metrics_by_group(df, "price_da", "y_pred", "hour")
        metrics_by_group(df, "price_da", "y_pred", "season")
    """
    rows = []
    for grp, sub in df.groupby(group_col):
        rows.append({
            group_col: grp,
            "MAE": mae(sub[y_true_col], sub[y_pred_col]),
            "RMSE": rmse(sub[y_true_col], sub[y_pred_col]),
            "sMAPE": smape(sub[y_true_col], sub[y_pred_col]),
            "n_obs": len(sub),
        })
    return pd.DataFrame(rows).sort_values(group_col).reset_index(drop=True)


def benchmark_table(results: dict) -> pd.DataFrame:
    """
    Construit un tableau de benchmark à partir d'un dict :
        {"Naive J-1": {"MAE": .., "RMSE": ..}, "XGBoost": {...}, ...}
    """
    return pd.DataFrame(results).T.sort_values("RMSE")
