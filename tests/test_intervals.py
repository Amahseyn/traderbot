from traderbot.ml.intervals import (
    DEFAULT_EVAL_TARGET_MINUTES,
    DEFAULT_FORECAST_HORIZONS,
    FORECAST_TARGET_MINUTES,
    default_eval_horizon,
    forecast_horizons_for_resolution,
)


def test_default_forecast_horizon_names():
    names = [name for _, name in DEFAULT_FORECAST_HORIZONS]
    assert names == ["1m", "5m", "1h", "2h", "4h", "6h", "12h", "1d"]
    assert FORECAST_TARGET_MINUTES == (1, 5, 60, 120, 240, 360, 720, 1440)


def test_forecast_horizons_on_1h_candles():
    horizons = forecast_horizons_for_resolution("60")
    labels = [label for _, label in horizons]
    assert labels == ["1h", "2h", "4h", "6h", "12h", "1d"]


def test_forecast_horizons_on_1m_candles():
    horizons = forecast_horizons_for_resolution("1")
    labels = [label for _, label in horizons]
    assert labels == ["1m", "5m", "1h", "2h", "4h", "6h", "12h", "1d"]


def test_default_eval_prefers_one_hour_on_60m():
    bars, bar_minutes = default_eval_horizon("60")
    assert bar_minutes == 60
    assert bars == 1
    assert bars * bar_minutes == DEFAULT_EVAL_TARGET_MINUTES


def test_default_eval_on_15m_includes_1h():
    bars, bar_minutes = default_eval_horizon("15")
    assert bar_minutes == 15
    assert bars * bar_minutes == 60
