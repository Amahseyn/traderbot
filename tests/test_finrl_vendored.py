"""Regression tests for traderbot's vendored FinRL core (traderbot.finrl).

Covers the ported modules and the point-in-time fix that upstream FinRL did not
have: min-variance weights in rolling mode must not use future prices.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from traderbot.finrl import (
    ema_cross_signals,
    split_validation_for_model_selection,
    zscore_normalize_indicators,
)
from traderbot.finrl.base_strategy import StrategyConfig
from traderbot.finrl.ml_strategy import MLStockSelectionStrategy


def test_ema_cross_signals_lag_one_bar() -> None:
    close = pd.Series([100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109] * 5)
    pos = ema_cross_signals(close, fast=3, slow=5)
    raw = (close.ewm(span=3, adjust=False).mean() > close.ewm(span=5, adjust=False).mean()).astype(int)
    for i in range(1, len(close)):
        assert int(pos.iloc[i]) == int(raw.iloc[i - 1])


def test_zscore_normalize_is_point_in_time() -> None:
    df = pd.DataFrame(
        {
            "date": pd.date_range("2020-03-31", periods=8, freq="QE"),
            "feat": [0.0, 1, 2, 3, 4, 5, 6, 7],
        }
    )
    as_of = df["date"].iloc[3]
    full = zscore_normalize_indicators(df, ["feat"], fit_end_date=as_of)
    tampered = df.copy()
    tampered.loc[tampered["date"] > as_of, "feat"] *= 100.0
    again = zscore_normalize_indicators(tampered, ["feat"], fit_end_date=as_of)
    in_window = full["date"] <= as_of
    # Fit statistics come from <= as_of only, so in-window values are unchanged.
    assert np.allclose(
        full.loc[in_window, "feat"].to_numpy(),
        again.loc[in_window, "feat"].to_numpy(),
    )


def test_split_validation_for_model_selection_is_disjoint() -> None:
    df = pd.DataFrame(
        {
            "date": pd.date_range("2020-01-01", periods=10, freq="D"),
            "v": range(10),
        }
    )
    selection, holdout = split_validation_for_model_selection(df)
    assert len(selection) and len(holdout)
    assert not set(selection["date"]).intersection(set(holdout["date"]))
    assert len(selection) + len(holdout) == len(df)


def _fundamentals(*, future_scale: float, tamper_after: int, n_quarters: int = 9) -> pd.DataFrame:
    dates = pd.date_range("2020-03-31", periods=n_quarters, freq="QE")
    rows = []
    for qi, datadate in enumerate(dates):
        for ti in range(2):
            price = 100.0 + qi * 4.0 + ti + (qi % 2)
            if qi > tamper_after:
                price *= future_scale
            rows.append(
                {
                    "gvkey": f"T{ti}",
                    "tic": f"T{ti}",
                    "datadate": datadate,
                    "adj_close_q": price,
                    "feat_a": float(qi),
                    "y_return": 0.02,
                    "y_return_provisional": False,
                }
            )
    return pd.DataFrame(rows)


def _rolling_weights(monkeypatch, fundamentals: pd.DataFrame, reb_date: pd.Timestamp) -> pd.DataFrame:
    strategy = MLStockSelectionStrategy(StrategyConfig(name="leak_regression"))
    # Disable concentration caps so the raw min-variance tilt is observable.
    strategy.config.max_weight_per_stock = 1.0  # type: ignore[attr-defined]
    strategy.config.max_sector_weight = 1.0  # type: ignore[attr-defined]

    preds = pd.DataFrame(
        {
            "date": [reb_date, reb_date],
            "gvkey": ["T0", "T1"],
            "predicted_return": [0.05, 0.06],
        }
    )
    monkeypatch.setattr(
        strategy,
        "_rolling_train_all_date",
        lambda **kwargs: preds,
        raising=True,
    )
    result = strategy.generate_weights(
        {"fundamentals": fundamentals},
        prediction_mode="rolling",
        weight_method="min_variance",
        top_quantile=0.0,
        lookback_periods=6,
    )
    return result.weights


def test_rolling_min_variance_ignores_future_prices(monkeypatch) -> None:
    reb_date = pd.Timestamp("2021-12-31")  # quarter index 7 of the 2020Q1.. series
    base = _rolling_weights(monkeypatch, _fundamentals(future_scale=1.0, tamper_after=7), reb_date)
    tampered = _rolling_weights(monkeypatch, _fundamentals(future_scale=50.0, tamper_after=7), reb_date)
    assert len(base) == 2
    merged = base.merge(tampered, on="gvkey", suffixes=("_base", "_tampered"))
    assert np.allclose(
        merged["weight_base"].to_numpy(), merged["weight_tampered"].to_numpy(), atol=1e-9
    ), f"rolling min-variance weights changed when future prices changed:\n{merged}"


def test_vendored_package_imports_without_sibling_repo() -> None:
    # Importing the package (not ml_strategy) must not require the sibling repo.
    import traderbot.finrl as finrl

    assert finrl.ema_cross_signals is not None
    assert finrl.MLStockSelectionStrategy is not None
