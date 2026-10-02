"""LightGBM eval across every default forecast horizon (synthetic OHLC, no export required)."""

from __future__ import annotations

import pytest
from helpers import require_lightgbm, synthetic_bars

from traderbot.ml.intervals import (
    DEFAULT_FORECAST_HORIZONS,
    default_eval_horizon,
    forecast_horizons_for_resolution,
    min_bars_for_forecast_eval,
    resolution_minutes,
)
from traderbot.ml.pipeline import run_forecast_eval
from traderbot.ml.simulator import final_equity_from_curve


@pytest.mark.parametrize(
    ("target_minutes", "name"),
    DEFAULT_FORECAST_HORIZONS,
    ids=[name for _, name in DEFAULT_FORECAST_HORIZONS],
)
def test_lightgbm_on_1m_bars_for_each_default_horizon(target_minutes: int, name: str):
    """Each default window (1m … 1d) as forward horizon on 1-minute candles."""
    require_lightgbm()
    from traderbot.ml.models.lightgbm import LightGBMForecastModel

    bar_minutes = 1
    horizon_bars = target_minutes // bar_minutes
    n = min_bars_for_forecast_eval(horizon_bars) + 150
    bars = synthetic_bars(n, bar_minutes=bar_minutes)
    result = run_forecast_eval(
        bars,
        LightGBMForecastModel(num_boost_round=12),
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
        train_ratio=0.8,
    )
    assert result.horizon_label == name
    assert len(result.y_true) >= 5
    assert result.metrics["n"] >= 5
    assert abs(final_equity_from_curve(result.extra["strategy_equity"]) - result.metrics["strategy_final_usd"]) < 1e-6


@pytest.mark.parametrize("resolution", ["1", "5", "15", "30", "60", "240", "D"])
def test_lightgbm_default_horizons_per_resolution(resolution: str):
    """Every horizon valid for a resolution runs end-to-end on synthetic data."""
    require_lightgbm()
    from traderbot.ml.models.lightgbm import LightGBMForecastModel

    bar_minutes = resolution_minutes(resolution)
    max_horizon = max(h for h, _ in forecast_horizons_for_resolution(resolution))
    n = min_bars_for_forecast_eval(max_horizon) + 100
    bars = synthetic_bars(n, bar_minutes=bar_minutes)

    for horizon_bars, label in forecast_horizons_for_resolution(resolution):
        need = min_bars_for_forecast_eval(horizon_bars)
        if len(bars) < need:
            continue
        result = run_forecast_eval(
            bars,
            LightGBMForecastModel(num_boost_round=10),
            horizon_bars=horizon_bars,
            bar_minutes=bar_minutes,
            train_ratio=0.8,
        )
        assert result.horizon_label == label
        assert len(result.y_pred) == len(result.y_true)


def test_default_eval_horizon_matches_named_window():
    for resolution in ("1", "5", "15", "30", "60", "180", "240", "D"):
        horizon_bars, bar_minutes = default_eval_horizon(resolution)
        total = horizon_bars * bar_minutes
        valid = {h * bar_minutes for h, _ in forecast_horizons_for_resolution(resolution)}
        assert total in valid or total == bar_minutes
