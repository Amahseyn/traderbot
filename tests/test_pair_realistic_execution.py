from __future__ import annotations

import math
import pytest

from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.backtesting.fills import calculate_market_impact, simulated_fill_price
from traderbot.backtesting.pair_engine import run_perp_pair_backtest


def _make_bar(symbol: str, timestamp: int, price: float, volume: float = 1000.0) -> dict:
    return {
        "symbol": symbol,
        "resolution": "60",
        "timestamp": timestamp,
        "open": price,
        "high": price * 1.002,
        "low": price * 0.998,
        "close": price,
        "volume": volume,
    }


def test_square_root_market_impact_scaling():
    """Verify that quadrupling order quantity exactly doubles market impact (square-root law)."""
    price = 100.0
    volatility = 0.02
    volume = 10_000.0
    gamma = 0.1

    impact_1 = calculate_market_impact(price, 100.0, volume, volatility, gamma)
    impact_4 = calculate_market_impact(price, 400.0, volume, volatility, gamma)

    assert impact_1 > 0
    assert math.isclose(impact_4, impact_1 * 2.0, rel_tol=1e-5), (
        f"Expected impact_4 ({impact_4}) to be exactly 2x impact_1 ({impact_1})"
    )


def test_simulated_fill_price_spread_crossing():
    """Verify taker orders cross half the spread and maker orders do not."""
    mid = 100.0
    spread = 0.002  # 20 bps

    buy_fill = simulated_fill_price("buy", mid, spread_pct=spread, is_maker=False)
    sell_fill = simulated_fill_price("sell", mid, spread_pct=spread, is_maker=False)
    maker_buy = simulated_fill_price("buy", mid, spread_pct=spread, is_maker=True)

    assert buy_fill > mid
    assert sell_fill < mid
    assert math.isclose(buy_fill, 100.1, rel_tol=1e-5)
    assert math.isclose(sell_fill, 99.9, rel_tol=1e-5)
    assert maker_buy == mid


def test_perp_pair_backtest_with_legging_latency():
    """Verify that legging_latency_bars delays Leg B fill, exposing unhedged price movement."""
    dominant_bars = []
    hedge_bars = []
    for index in range(50):
        t = index * 3600
        p_d = 100.0
        # Spread diverges from bar 25 onwards
        p_h = 100.0 if index < 25 else 130.0
        dominant_bars.append(_make_bar("BTCUSDT", t, p_d))
        hedge_bars.append(_make_bar("ETHUSDT", t, p_h))

    algo = PairTradingAlgorithm(lookback_period=20, entry_threshold=1.5, exit_threshold=0.5)
    result = run_perp_pair_backtest(
        algo,
        dominant_bars,
        hedge_bars,
        initial_cash=10_000.0,
        legging_latency_bars=2,
    )
    # Check that Leg A and Leg B entry trade timestamps differ by legging_latency_bars * 3600
    dominant_entries = [t for t in result.trades if t.leg == "dominant" and t.action == "buy"]
    hedge_entries = [t for t in result.trades if t.leg == "hedge" and t.action == "sell"]
    assert len(dominant_entries) > 0
    assert len(hedge_entries) > 0
    assert hedge_entries[0].timestamp - dominant_entries[0].timestamp == 2 * 3600

