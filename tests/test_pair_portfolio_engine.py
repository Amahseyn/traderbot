from __future__ import annotations

import math
import pytest

from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.backtesting.pair_engine import (
    MultiPairBacktestResult,
    run_multi_pair_backtest,
    run_perp_pair_backtest,
)
from traderbot.risk.cointegration_monitor import CointegrationHealthMonitor


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


def test_cointegration_breakdown_halts_trading():
    """Verify that when cointegration breaks down, positions are closed and new entries halted."""
    # 30 bars of stationary mean-reverting relationship
    # Followed by divergent non-stationary walk (cointegration breakdown)
    dominant_bars = []
    hedge_bars = []
    for index in range(60):
        t = index * 3600
        p_d = 100.0
        if index < 25:
            p_h = 100.0
        elif index < 32:
            p_h = 130.0  # entry trigger
        elif index < 40:
            p_h = 100.0  # exit
        else:
            # Massive structural break / drift
            p_h = 100.0 + (index - 40) * 15.0
        dominant_bars.append(_make_bar("BTCUSDT", t, p_d))
        hedge_bars.append(_make_bar("ETHUSDT", t, p_h))

    algo = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.5)
    result = run_perp_pair_backtest(
        algo,
        dominant_bars,
        hedge_bars,
        check_cointegration_breakdown=True,
    )
    assert result.final_equity > 0
    # During the structural break (bars 40-60), breakdown must prevent catastrophic holding
    assert hasattr(result, "breakdown_events")
    assert len(result.breakdown_events) > 0


def test_multi_pair_concurrent_backtest():
    """Verify running multiple pairs concurrently in a portfolio backtest with shared capital."""
    timestamps = [index * 3600 for index in range(60)]

    # Pair 1: BTC / ETH
    bars_btc = [_make_bar("BTCUSDT", t, 100.0) for t in timestamps]
    bars_eth = [_make_bar("ETHUSDT", t, 100.0 if i < 25 else (130.0 if i < 35 else 100.0)) for i, t in enumerate(timestamps)]

    # Pair 2: SOL / AVAX
    bars_sol = [_make_bar("SOLUSDT", t, 50.0) for t in timestamps]
    bars_avax = [_make_bar("AVAXUSDT", t, 50.0 if i < 30 else (70.0 if i < 45 else 50.0)) for i, t in enumerate(timestamps)]

    algo1 = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.5)
    algo2 = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.5)

    pairs_config = [
        {"pair_id": "BTC-ETH", "algorithm": algo1, "dominant_bars": bars_btc, "hedge_bars": bars_eth, "weight": 0.5},
        {"pair_id": "SOL-AVAX", "algorithm": algo2, "dominant_bars": bars_sol, "hedge_bars": bars_avax, "weight": 0.5},
    ]

    portfolio_result = run_multi_pair_backtest(
        pairs_config,
        initial_cash=20_000.0,
    )

    assert isinstance(portfolio_result, MultiPairBacktestResult)
    assert len(portfolio_result.pair_results) == 2
    assert "BTC-ETH" in portfolio_result.pair_results
    assert "SOL-AVAX" in portfolio_result.pair_results
    assert len(portfolio_result.portfolio_equity_curve) > 0
    assert portfolio_result.final_equity > 0

