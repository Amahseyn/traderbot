from pathlib import Path

from traderbot.algorithms.forecast_gate import (
    combine_forecast_with_rule_signal,
    forecast_direction_signal,
)
from traderbot.algorithms.patterns import double_bottom_score
from traderbot.algorithms.registry import algorithm_for_id, backtest_strategy_ids
from traderbot.algorithms.strategies.chart_patterns import ChartPatternsAlgorithm
from traderbot.algorithms.strategies.breakout_atr import BreakoutAtrAlgorithm
from traderbot.algorithms.strategies.forecast_signal import ForecastSignalAlgorithm
from traderbot.algorithms.strategies.ml_gated import MlGatedAlgorithm
from traderbot.backtesting import run_backtest
from traderbot.ml.forecasts import load_forecast_by_timestamp, write_holdout_forecasts
from traderbot.ml.results import ModelRunResult


def _bar(index: int, close: float, high: float | None = None, low: float | None = None) -> dict:
    high_price = high if high is not None else close + 0.5
    low_price = low if low is not None else close - 0.5
    return {
        "symbol": "BTCIRT",
        "resolution": "60",
        "timestamp": index * 3600,
        "datetime_utc": "",
        "open": close,
        "high": high_price,
        "low": low_price,
        "close": close,
        "volume": 1.0,
    }


def test_forecast_direction_signal_threshold():
    assert forecast_direction_signal(0.01, forecast_threshold=0.0) == "buy"
    assert forecast_direction_signal(-0.01, forecast_threshold=0.0) == "sell"
    assert forecast_direction_signal(0.0, forecast_threshold=0.0) == "hold"


def test_combine_forecast_with_rule_signal_modes():
    assert (
        combine_forecast_with_rule_signal(
            "buy",
            0.02,
            gate_mode="forecast_filters_rule",
            forecast_threshold=0.0,
        )
        == "buy"
    )
    assert (
        combine_forecast_with_rule_signal(
            "buy",
            -0.02,
            gate_mode="forecast_filters_rule",
            forecast_threshold=0.0,
        )
        == "hold"
    )
    assert (
        combine_forecast_with_rule_signal(
            "hold",
            0.02,
            gate_mode="rule_filters_forecast",
            forecast_threshold=0.0,
        )
        == "hold"
    )


def test_breakout_atr_runs_backtest():
    bars = [_bar(index, 100.0 + index * 0.1) for index in range(40)]
    result = run_backtest(BreakoutAtrAlgorithm(), bars, initial_cash=1000.0)
    assert len(result.equity_curve) == len(bars)


def test_chart_patterns_runs_backtest():
    bars = [_bar(index, 100.0) for index in range(30)]
    result = run_backtest(ChartPatternsAlgorithm(), bars, initial_cash=1000.0)
    assert len(result.equity_curve) == len(bars)


def test_forecast_signal_uses_timestamp_map():
    bars = [_bar(0, 100.0), _bar(1, 101.0), _bar(2, 102.0)]
    algo = ForecastSignalAlgorithm(forecast_by_timestamp={bars[1]["timestamp"]: 0.05})
    assert algo.on_bar(bars[0]) == "hold"
    assert algo.on_bar(bars[1]) == "buy"
    assert algo.on_bar(bars[2]) == "hold"


def test_ml_gated_wraps_inner_strategy():
    bars = [_bar(index, 100.0 - index) for index in range(20)]
    inner = algorithm_for_id("rsi_threshold", period=3, oversold=40.0, overbought=60.0)
    algo = MlGatedAlgorithm(
        inner=inner,
        forecast_by_timestamp={bars[-1]["timestamp"]: 0.1},
        gate_mode="forecast_filters_rule",
    )
    actions = [algo.on_bar(bar) for bar in bars]
    assert "hold" in actions


def test_holdout_forecasts_round_trip(tmp_path: Path):
    result = ModelRunResult(
        model_id="lightgbm",
        horizon_label="4h",
        horizon_bars=4,
        feature_names=["close"],
        timestamps=[1, 2, 3],
        y_true=[0.01, -0.01, 0.02],
        y_pred=[0.02, -0.02, 0.03],
        metrics={"n": 3.0, "mae": 0.0, "rmse": 0.0, "directional_accuracy": 1.0},
    )
    path = tmp_path / "holdout_forecasts.json"
    write_holdout_forecasts(result, path)
    loaded = load_forecast_by_timestamp(path)
    assert loaded[3] == 0.03


def test_backtest_strategy_ids_excludes_forecast_without_flag():
    ids = backtest_strategy_ids(include_forecast_strategies=False)
    assert "forecast_signal" not in ids
    assert "chart_patterns" in ids
    assert backtest_strategy_ids(include_forecast_strategies=True) == sorted(
        set(ids) | {"forecast_signal", "ml_gated"}
    )


def test_double_bottom_score_zero_on_flat_series():
    lows = [10.0] * 20
    highs = [10.5] * 20
    closes = [10.0] * 20
    assert double_bottom_score(lows, highs, closes) == 0.0


def test_ml_features_include_pattern_columns():
    from traderbot.ml.features import build_feature_rows

    bars = [_bar(index, 100.0 + index * 0.01) for index in range(25)]
    rows = build_feature_rows(bars)
    assert "pattern_double_bottom_score" in rows[-1]
    assert "pattern_double_top_score" in rows[-1]
