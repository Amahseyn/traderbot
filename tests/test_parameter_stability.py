from __future__ import annotations

import math
import pytest

from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.backtesting.pair_engine import run_perp_pair_backtest
from traderbot.backtesting.report import pair_backtest_summary_dict
from traderbot.backtesting.walk_forward import (
    PairWalkForwardOptions,
    run_pair_walk_forward,
)


def _make_bar(symbol: str, timestamp: int, price: float) -> dict:
    return {
        "symbol": symbol,
        "resolution": "60",
        "timestamp": timestamp,
        "open": price,
        "high": price * 1.001,
        "low": price * 0.999,
        "close": price,
        "volume": 100.0,
    }


def test_parameter_stability_metrics_reported():
    bar_count = 180
    timestamps = [index * 3600 for index in range(bar_count)]
    dominant_bars = [_make_bar("BTCUSDT", t, 100.0 + (i % 6) * 0.3) for i, t in enumerate(timestamps)]
    hedge_bars = [_make_bar("ETHUSDT", t, 50.0 + (i % 6) * 0.15) for i, t in enumerate(timestamps)]

    options = PairWalkForwardOptions(
        param_grid={
            "entry_threshold": [1.2, 1.8],
            "exit_threshold": [0.4, 0.6],
        },
        dominant_bars=dominant_bars,
        hedge_bars=hedge_bars,
        train_bars=60,
        test_bars=30,
        warmup_bars=15,
        purge_bars=2,
        window_mode="rolling",
    )

    result = run_pair_walk_forward(options)
    stability = result["parameter_stability"]

    assert "entry_threshold" in stability
    assert "exit_threshold" in stability
    assert "values_across_folds" in stability["entry_threshold"]
    assert "dispersion_cv" in stability["entry_threshold"]
    assert stability["entry_threshold"]["unique_count"] >= 1


def test_pair_backtest_summary_dict_reporting():
    bar_count = 60
    timestamps = [index * 3600 for index in range(bar_count)]
    dominant_bars = [_make_bar("BTCUSDT", t, 100.0) for t in timestamps]
    hedge_bars = [_make_bar("ETHUSDT", t, 100.0 if i < 25 else (130.0 if i < 35 else 100.0)) for i, t in enumerate(timestamps)]

    algo = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.5)
    result = run_perp_pair_backtest(
        algo,
        dominant_bars,
        hedge_bars,
        initial_cash=10_000.0,
        fee_rate=0.0005,
        slippage_rate=0.0005,
        funding_rates={30 * 3600: (0.001, 0.001)},
    )

    benchmarks = {"buy_hold_a_pct": 0.0, "buy_hold_b_pct": 0.0, "equal_weight_pct": 0.0}
    summary = pair_backtest_summary_dict(result, bars=bar_count, benchmarks=benchmarks)

    assert summary["bars"] == bar_count
    assert "annualized_sharpe" in summary
    assert "annualized_sortino" in summary
    assert "calmar_ratio" in summary
    assert "turnover_ratio" in summary
    assert "exposure_time_pct" in summary
    assert summary["total_fees"] > 0
    assert summary["total_funding_paid"] > 0
    assert summary["total_funding_received"] > 0
    assert summary["benchmarks"] == benchmarks
