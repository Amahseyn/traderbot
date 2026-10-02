import pytest

from traderbot.algorithms.strategies import SmaCrossAlgorithm
from traderbot.backtest import run_backtest
from traderbot.backtest_vectorbt import infer_bar_freq, vectorbt_metrics_dict

vectorbt = pytest.importorskip("vectorbt")


def _bars(closes: list[float]) -> list[dict]:
    return [
        {
            "symbol": "BTCIRT",
            "resolution": "D",
            "timestamp": i * 3600,
            "datetime_utc": "",
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "volume": 1.0,
        }
        for i, c in enumerate(closes)
    ]


def test_infer_bar_freq_hourly():
    bars = _bars([1.0, 2.0, 3.0])
    freq = infer_bar_freq(bars)
    assert freq is not None
    assert freq.total_seconds() == 3600.0


def test_vectorbt_metrics_align_with_builtin_backtest():
    closes = [1, 2, 3, 2, 1, 2, 3, 4, 3, 2]
    bars = _bars(closes)
    algo = SmaCrossAlgorithm(fast=2, slow=3)
    result = run_backtest(algo, bars, initial_cash=1000.0, fee_rate=0.0)
    metrics = vectorbt_metrics_dict(
        algo,
        bars,
        initial_cash=1000.0,
        fee_rate=0.0,
    )
    assert "total_return_pct" in metrics
    assert metrics["total_return_pct"] is not None
    assert abs(metrics["total_return_pct"] - result.return_pct) < 0.05
