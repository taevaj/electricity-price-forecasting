"""
plots.py
--------
Fonctions de visualisation réutilisables (10-15 graphiques clés attendus,
section 14). Squelette à enrichir au fil des notebooks EDA / analyse.
"""

import matplotlib.pyplot as plt
import pandas as pd


def plot_price_series(df: pd.DataFrame, price_col: str = "price_da", ax=None, title="Prix day-ahead (€/MWh)"):
    ax = ax or plt.gca()
    df[price_col].plot(ax=ax, linewidth=0.6)
    ax.set_title(title)
    ax.set_ylabel("€/MWh")
    return ax


def plot_price_distribution(df: pd.DataFrame, price_col: str = "price_da", ax=None):
    ax = ax or plt.gca()
    df[price_col].plot(kind="hist", bins=100, ax=ax)
    ax.set_title("Distribution des prix day-ahead")
    ax.set_xlabel("€/MWh")
    return ax


def plot_avg_profile_by_hour(df: pd.DataFrame, price_col: str = "price_da", hour_col: str = "hour", ax=None):
    ax = ax or plt.gca()
    df.groupby(hour_col)[price_col].mean().plot(kind="bar", ax=ax)
    ax.set_title("Prix moyen par heure de la journée")
    ax.set_ylabel("€/MWh")
    return ax


def plot_residual_load_vs_price(df: pd.DataFrame, residual_col="residual_load", price_col="price_da", ax=None):
    ax = ax or plt.gca()
    ax.scatter(df[residual_col], df[price_col], s=3, alpha=0.3)
    ax.set_title("Prix vs Residual Load")
    ax.set_xlabel("Residual Load (MW)")
    ax.set_ylabel("€/MWh")
    return ax


def plot_error_by_group(metrics_df: pd.DataFrame, group_col: str, metric_col: str = "RMSE", ax=None):
    """Utilise la sortie de metrics.metrics_by_group()."""
    ax = ax or plt.gca()
    metrics_df.plot(x=group_col, y=metric_col, kind="bar", ax=ax, legend=False)
    ax.set_title(f"{metric_col} par {group_col}")
    return ax


def plot_forecast_vs_actual(y_true: pd.Series, y_pred: pd.Series, ax=None, title="Prévision vs réel"):
    ax = ax or plt.gca()
    ax.plot(y_true.index, y_true.values, label="Réel", linewidth=0.8)
    ax.plot(y_true.index, y_pred, label="Prévision", linewidth=0.8, alpha=0.8)
    ax.set_title(title)
    ax.legend()
    return ax
