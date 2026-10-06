import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src import backtest, data, features, models


def sample_frame(periods=24 * 40):
    index = pd.date_range("2024-01-01", periods=periods, freq="h", tz="UTC")
    values = np.arange(periods, dtype=float)
    return pd.DataFrame(
        {
            "price_da": values,
            "demand_forecast": 100.0,
            "wind_forecast": 20.0,
            "solar_forecast": 10.0,
            "hour": index.hour,
        }, index=index,
    )


class TemporalIntegrityTests(unittest.TestCase):
    def test_splits_are_disjoint(self):
        train, val, test = backtest.chronological_split(
            sample_frame(), "2024-01-10", "2024-01-20"
        )
        self.assertTrue(train.index.intersection(val.index).empty)
        self.assertTrue(val.index.intersection(test.index).empty)

    def test_duplicate_index_is_rejected(self):
        frame = sample_frame(48)
        duplicate = pd.concat([frame, frame.iloc[[0]]]).sort_index()
        with self.assertRaises(ValueError):
            backtest.chronological_split(duplicate, "2024-01-02", "2024-01-03")

    def test_walk_forward_windows_are_disjoint(self):
        frame = sample_frame()
        previous_test = None
        for window in backtest.walk_forward_windows(frame, 10, 7, 7):
            train = frame.loc[(frame.index >= window.train_start) & (frame.index < window.train_end)]
            test = frame.loc[(frame.index >= window.test_start) & (frame.index < window.test_end)]
            self.assertTrue(train.index.intersection(test.index).empty)
            self.assertEqual(len(test), 168)
            if previous_test is not None:
                self.assertTrue(previous_test.intersection(test.index).empty)
            previous_test = test.index

    def test_runner_never_fits_on_test_timestamp(self):
        frame = sample_frame()
        fitted = []

        def fit_fn(x_train, y_train):
            fitted.append(x_train.index)
            return float(y_train.mean())

        def predict_fn(model, x_test):
            self.assertTrue(fitted[-1].intersection(x_test.index).empty)
            return np.full(len(x_test), model)

        result = backtest.run_walk_forward(
            frame, ["demand_forecast"], "price_da", fit_fn, predict_fn, 10, 7, 7
        )
        self.assertFalse(result.empty)
        self.assertFalse(result["datetime"].duplicated().any())


class FeatureLeakageTests(unittest.TestCase):
    def test_pipeline_excludes_target_labels_and_short_lag(self):
        output = features.build_feature_pipeline(sample_frame())
        self.assertNotIn("negative_price_flag", output)
        self.assertNotIn("spike_flag", output)
        self.assertNotIn("price_da_lag_1", output)
        self.assertIn("price_da_lag_1d", output)

    def test_absolute_24_hour_lag_is_rejected(self):
        with self.assertRaises(ValueError):
            features.add_price_lags(sample_frame(), lags=(24,))

    def test_day_lag_never_uses_target_day_across_dst(self):
        index = pd.date_range("2024-10-25", "2024-10-29", freq="h", inclusive="left", tz="UTC")
        frame = pd.DataFrame({"price_da": np.arange(len(index), dtype=float)}, index=index)
        lagged = features.add_price_day_lags(frame, day_lags=(1,))
        local_dates = lagged.index.tz_convert("Europe/Paris").date
        for position, value in enumerate(lagged["price_da_lag_1d"]):
            if not pd.isna(value):
                self.assertLess(local_dates[int(value)], local_dates[position])

    def test_spike_threshold_is_fitted_on_train(self):
        train = sample_frame(100)
        threshold = features.fit_spike_threshold(train, spike_quantile=0.95)
        future = sample_frame(10)
        future["price_da"] = 10_000.0
        labelled = features.add_regime_flags(future, threshold)
        self.assertEqual(threshold, float(train["price_da"].quantile(0.95)))
        self.assertTrue(labelled["spike_flag"].eq(1).all())


class BaselineAndRawTests(unittest.TestCase):
    def test_hour_mean_is_fitted_only_on_train(self):
        train = sample_frame(48)
        test = sample_frame(24)
        test["price_da"] = 100_000.0
        prediction = models.predict_mean_by_hour(test, models.fit_mean_by_hour(train))
        self.assertEqual(prediction.iloc[0], 12.0)

    def test_j1_uses_previous_local_date(self):
        frame = sample_frame(72)
        prediction = models.naive_persistence(frame, day_lag=1)
        local_dates = frame.index.tz_convert("Europe/Paris").date
        for position, value in enumerate(prediction):
            if not pd.isna(value):
                source = int(frame.index.get_loc(frame.index[frame["price_da"].eq(value)][0]))
                self.assertLess(local_dates[source], local_dates[position])

    def test_raw_export_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            data.save_raw(sample_frame(2), "prices", raw_dir=directory)
            with self.assertRaises(FileExistsError):
                data.save_raw(sample_frame(2), "prices", raw_dir=directory)
            self.assertTrue(Path(directory, "prices.csv").exists())


if __name__ == "__main__":
    unittest.main()
