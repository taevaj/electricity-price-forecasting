"""
backtest.py
-----------
Validation chronologique et walk-forward backtesting (section 11 du cahier
de projet). Squelette à implémenter au notebook 09.
"""

from dataclasses import dataclass
from typing import Callable, Iterator

import pandas as pd


@dataclass
class WalkForwardWindow:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def _validate_time_index(df: pd.DataFrame) -> None:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError("df.index doit être un DatetimeIndex")
    if not df.index.is_monotonic_increasing:
        raise ValueError("df.index doit être trié par ordre chronologique")
    if not df.index.is_unique:
        raise ValueError("df.index doit être unique avant tout split")


def _align_boundary(value: str | pd.Timestamp, index: pd.DatetimeIndex) -> pd.Timestamp:
    boundary = pd.Timestamp(value)
    if index.tz is None:
        if boundary.tzinfo is not None:
            boundary = boundary.tz_localize(None)
    elif boundary.tzinfo is None:
        boundary = boundary.tz_localize(index.tz)
    else:
        boundary = boundary.tz_convert(index.tz)
    return boundary


def chronological_split(df: pd.DataFrame, train_end: str, val_end: str):
    """
    Split sans chevauchement : train < train_end,
    train_end <= validation < val_end, test >= val_end.
    """
    _validate_time_index(df)
    train_boundary = _align_boundary(train_end, df.index)
    val_boundary = _align_boundary(val_end, df.index)
    if train_boundary >= val_boundary:
        raise ValueError("train_end doit être strictement antérieur à val_end")
    train = df.loc[df.index < train_boundary]
    val = df.loc[(df.index >= train_boundary) & (df.index < val_boundary)]
    test = df.loc[df.index >= val_boundary]
    return train, val, test


def walk_forward_windows(
    df: pd.DataFrame,
    initial_train_days: int,
    test_days: int,
    step_days: int,
    mode: str = "expanding",
) -> Iterator[WalkForwardWindow]:
    """
    Génère les fenêtres successives d'un walk-forward backtest.

    mode : "expanding" (le train grandit) ou "rolling" (fenêtre de train fixe,
    on ne garde que les N derniers jours).
    """
    _validate_time_index(df)
    if initial_train_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("Les tailles de fenêtres doivent être strictement positives")
    freq = pd.Timedelta(days=1)
    start = df.index.min()
    step = df.index.to_series().diff().dropna().median() if len(df.index) > 1 else pd.Timedelta(hours=1)
    end_exclusive = df.index.max() + step

    train_end = start + initial_train_days * freq
    while train_end + test_days * freq <= end_exclusive:
        test_start = train_end
        test_end = train_end + test_days * freq

        if mode == "expanding":
            train_start = start
        elif mode == "rolling":
            train_start = train_end - initial_train_days * freq
        else:
            raise ValueError("mode doit être 'expanding' ou 'rolling'")

        yield WalkForwardWindow(train_start, train_end, test_start, test_end)
        train_end = train_end + step_days * freq


def run_walk_forward(
    df: pd.DataFrame,
    feature_cols: list,
    target_col: str,
    fit_fn: Callable,
    predict_fn: Callable,
    initial_train_days: int = 365,
    test_days: int = 7,
    step_days: int = 7,
    mode: str = "expanding",
) -> pd.DataFrame:
    """
    Boucle générique de walk-forward backtesting.

    fit_fn(X_train, y_train) -> model
    predict_fn(model, X_test) -> y_pred

    Returns
    -------
    pd.DataFrame avec colonnes: datetime, y_true, y_pred, window_id
    """
    results = []
    for i, window in enumerate(
        walk_forward_windows(df, initial_train_days, test_days, step_days, mode)
    ):
        train = df.loc[(df.index >= window.train_start) & (df.index < window.train_end)]
        test = df.loc[(df.index >= window.test_start) & (df.index < window.test_end)]
        if train.empty or test.empty:
            continue
        if not train.index.intersection(test.index).empty:
            raise RuntimeError("Chevauchement détecté entre train et test")

        model = fit_fn(train[feature_cols], train[target_col])
        y_pred = predict_fn(model, test[feature_cols])

        chunk = pd.DataFrame({
            "datetime": test.index,
            "y_true": test[target_col].values,
            "y_pred": y_pred,
            "window_id": i,
        })
        results.append(chunk)

    return pd.concat(results, ignore_index=True) if results else pd.DataFrame()
