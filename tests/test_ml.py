import math

import pytest

from traderbot.ml.dataset import build_supervised, horizon_label
from traderbot.ml.features import build_feature_rows, forward_log_return, rsi
from traderbot.ml.metrics import format_metrics_block, full_metrics, regression_metrics
from traderbot.ml.pipeline import run_forecast_eval
from traderbot.ml.registry import list_models
from traderbot.ml.results import save_run_result
from traderbot.ml.simulator import simulate_holdout_account


def synthetic_bars(n = 120, *, start = 100.0) -> list[dict]:
    bars = []
    price = start
    for i in range(n):
        price *= 1.0 + 0.002 * math.sin(i / 7.0) + 0.0005 * (i % 5 - 2)
        bars.append(
            {
                "timestamp": 1_700_000_000 + i * 3600,
                "open": price * 0.999,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price,
                "volume": 1000.0 + i,
            }
        )
    return bars


def test_horizon_label():
    assert horizon_label(60, 4) == "4h"
    assert horizon_label(60, 24) == "1d"


def test_rsi_and_forward_return():
    closes = [10.0 + i * 0.1 for i in range(40)]
    r = rsi(closes, period=14)
    assert r[14] is not None
    fwd = forward_log_return(closes, 4)
    assert fwd[-1] is None
    assert fwd[0] is not None


def test_build_supervised_shapes():
    bars = synthetic_bars(80)
    xs, ys, ts, cols, label_ends = build_supervised(bars, horizon_bars=4, bar_minutes=60)
    assert len(label_ends) == len(ts)
    assert len(xs) == len(ys) == len(ts)
    assert len(cols) >= 11
    assert all(len(x) == len(cols) for x in xs)


def test_regression_metrics_perfect():
    m = regression_metrics([0.1, -0.2], [0.1, -0.2])
    assert m["mae"] == 0.0
    assert m["directional_accuracy"] == 1.0
    block = format_metrics_block(m)
    assert "MAE" in block and "RMSE" in block


def test_sample_100_usd_metrics():
    y_true = [0.01, -0.02, 0.03]
    y_pred = [0.1, -0.1, 0.1]
    ts = [1000, 4600, 8200]
    prices = [(0, 100.0), (1000, 101.0), (4600, 99.0), (8200, 102.0), (11800, 105.0)]
    sim = simulate_holdout_account(
        y_true,
        y_pred,
        ts,
        horizon_bars=1,
        bar_minutes=60,
        price_series=prices,
        initial_usd=100.0,
    )
    assert sim.metrics["initial_usd"] == 100.0
    m = full_metrics(y_true, y_pred, initial_usd=100.0, simulation=sim)
    block = format_metrics_block(m)
    assert "Sample $100" in block
    assert "Benefit vs B&H" in block


def test_catalog_includes_lgbm_and_chronos():
    ids = {m.id for m in list_models()}
    assert "lightgbm" in ids and "chronos" in ids
    impl = {m.id for m in list_models(implemented_only=True)}
    assert impl == {"lightgbm", "chronos"}


def _require_lightgbm():
    try:
        import lightgbm as lgb

        return lgb
    except (ImportError, OSError) as exc:
        pytest.skip(f"lightgbm unavailable: {exc}")


def test_lightgbm_run_and_visualization(tmp_path):
    _require_lightgbm()
    pytest.importorskip("matplotlib")

    from traderbot.ml.models.lightgbm import LightGBMForecastModel

    bars = synthetic_bars(100)
    result = run_forecast_eval(
        bars,
        LightGBMForecastModel(num_boost_round=20),
        horizon_bars=4,
        bar_minutes=60,
        train_ratio=0.75,
    )
    assert result.model_id == "lightgbm"
    assert len(result.y_true) == len(result.y_pred) > 0
    assert "mae" in result.metrics
    assert result.extra.get("feature_importance")

    out = tmp_path / "lgbm_4h"
    save_run_result(result, out)
    assert (out / "results.json").is_file()
    assert result.visualization is not None
    assert result.visualization.actual_vs_predicted.is_file()
    assert "visualizations" in str(result.visualization.actual_vs_predicted)
    assert result.visualization.residuals.is_file()
    assert result.visualization.feature_importance is not None


@pytest.mark.integration
def test_chronos_run_and_visualization(tmp_path):
    pytest.importorskip("chronos")
    pytest.importorskip("torch")
    pytest.importorskip("matplotlib")

    from traderbot.ml.models.chronos import ChronosForecastModel

    bars = synthetic_bars(80)
    result = run_forecast_eval(
        bars,
        ChronosForecastModel(),
        horizon_bars=4,
        bar_minutes=60,
        train_ratio=0.7,
    )
    assert result.model_id == "chronos"
    assert len(result.y_true) == len(result.y_pred) > 0
    out = tmp_path / "chronos_4h"
    save_run_result(result, out)
    assert (out / "results.json").is_file()
    assert result.visualization is not None


def test_feature_rows_match_bars():
    bars = synthetic_bars(35)
    rows = build_feature_rows(bars)
    assert len(rows) == len(bars)
    assert rows[-1]["close"] == bars[-1]["close"]
