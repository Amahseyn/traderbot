from __future__ import annotations

import math
import numpy as np
import pytest

from traderbot.algorithms.pair_trading.sizing import (
    PairSizingResult,
    calculate_pair_position_sizes,
)
from traderbot.algorithms.pair_trading.spread import (
    cointegration_spread_z_score_from_closes,
    spread_z_score_from_closes,
)
from traderbot.algorithms.pair_trading.state import PairStateManager
from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.analysis.pairs.models import RankedPairResult
from traderbot.backtesting.pair_engine import (
    run_pair_backtest,
    run_pair_backtest_for_exchange,
    run_perp_pair_backtest,
)


def _make_bars(closes: list[float], symbol: str = "BTCUSDT", start_time: int = 1_000_000) -> list[dict]:
    return [
        {
            "symbol": symbol,
            "resolution": "60",
            "timestamp": start_time + index * 3600,
            "open": price,
            "high": price * 1.002,
            "low": price * 0.998,
            "close": price,
            "volume": 100.0,
        }
        for index, price in enumerate(closes)
    ]


def test_cointegration_spread_calculation_causality():
    """Verify S_t = ln(A_t) - alpha - beta * ln(B_t) and causal rolling z-score."""
    closes_a = [100.0 + (i % 5) * 0.5 for i in range(50)]
    closes_b = [50.0 + (i % 5) * 0.25 for i in range(50)]
    hedge_ratio = 0.8
    intercept = 0.1

    snapshot = cointegration_spread_z_score_from_closes(
        np.asarray(closes_a),
        np.asarray(closes_b),
        lookback_period=30,
        hedge_ratio=hedge_ratio,
        intercept=intercept,
    )
    assert snapshot is not None
    assert snapshot.spread_model == "cointegration"

    # Check exact mathematical spread value at current bar
    expected_s_last = math.log(closes_a[-1]) - intercept - hedge_ratio * math.log(closes_b[-1])
    assert math.isclose(snapshot.spread_pct, expected_s_last, rel_tol=1e-7)

    # Causality test: changing future bars does not change snapshot at index 40
    snap_40 = cointegration_spread_z_score_from_closes(
        np.asarray(closes_a[:40]),
        np.asarray(closes_b[:40]),
        lookback_period=30,
        hedge_ratio=hedge_ratio,
        intercept=intercept,
    )
    assert snap_40 is not None
    # Modifying later bars in full list
    closes_a_mutated = list(closes_a)
    closes_a_mutated[45] *= 2.0
    snap_40_after = cointegration_spread_z_score_from_closes(
        np.asarray(closes_a_mutated[:40]),
        np.asarray(closes_b[:40]),
        lookback_period=30,
        hedge_ratio=hedge_ratio,
        intercept=intercept,
    )
    assert math.isclose(snap_40.z_score, snap_40_after.z_score, rel_tol=1e-9)


def _generate_synthetic_pair(n_bars: int = 40, seed: int = 42) -> tuple[list[float], list[float]]:
    np.random.seed(seed)
    base = 100.0 + np.sin(np.linspace(0, 3, n_bars)) * 2.0
    a = list(base + np.random.normal(0, 0.15, n_bars))
    b = list(base + np.random.normal(0, 0.15, n_bars))
    return a, b


def test_long_spread_direction_mathematics():
    """
    Mathematical validation:
    When Spread is abnormally low (Z <= -2.0), Asset A is undervalued vs B.
    Mean-reversion predicts Spread will rise: Long A, Short B.
    Strategy must emit 'long_spread'.
    """
    a, b = _generate_synthetic_pair(40)
    algo = PairTradingAlgorithm(
        lookback_period=20,
        entry_threshold=2.0,
        exit_threshold=0.5,
        hedge_ratio=1.0,
        intercept=0.0,
        spread_model="cointegration",
    )

    for i in range(len(a) - 1):
        algo.pair_signal({"close": a[i], "hedge_close": b[i], "timestamp": i * 60})

    # Cause spread to drop into entry band (-3.0 < Z <= -2.0)
    signal = algo.pair_signal({"close": a[-1] - 1.0, "hedge_close": b[-1], "timestamp": (len(a) - 1) * 60})
    assert signal == "long_spread"
    assert algo._spread_position == "long_spread"
    assert algo.state == "OPEN"


def test_short_spread_direction_mathematics():
    """
    Mathematical validation:
    When Spread is abnormally high (Z >= +2.0), Asset A is overvalued vs B.
    Mean-reversion predicts Spread will fall: Short A, Long B.
    Strategy must emit 'short_spread'.
    """
    a, b = _generate_synthetic_pair(40)
    algo = PairTradingAlgorithm(
        lookback_period=20,
        entry_threshold=2.0,
        exit_threshold=0.5,
        hedge_ratio=1.0,
        intercept=0.0,
        spread_model="cointegration",
    )

    for i in range(len(a) - 1):
        algo.pair_signal({"close": a[i], "hedge_close": b[i], "timestamp": i * 60})

    # Cause spread to rise into entry band (+2.0 <= Z < +4.0)
    signal = algo.pair_signal({"close": a[-1] + 0.8, "hedge_close": b[-1], "timestamp": (len(a) - 1) * 60})
    assert signal == "short_spread"
    assert algo._spread_position == "short_spread"
    assert algo.state == "OPEN"


def test_reversion_exit_and_zscore_stop():
    """Test normal reversion exit at |Z| <= exit_threshold and emergency stop at |Z| >= stop_threshold."""
    a, b = _generate_synthetic_pair(40)
    algo = PairTradingAlgorithm(
        lookback_period=20,
        entry_threshold=2.0,
        exit_threshold=0.5,
        stop_threshold=4.0,
        spread_model="cointegration",
    )
    for i in range(len(a) - 1):
        algo.pair_signal({"close": a[i], "hedge_close": b[i], "timestamp": i * 60})

    # Trigger long spread
    sig_entry = algo.pair_signal({"close": a[-1] - 1.0, "hedge_close": b[-1], "timestamp": 40 * 60})
    assert sig_entry == "long_spread"

    # Reversion back to equilibrium
    sig_exit = algo.pair_signal({"close": a[-1], "hedge_close": b[-1], "timestamp": 41 * 60})
    assert sig_exit == "close_spread"
    assert algo._spread_position == "flat"

    # Now test stop loss trigger
    algo.reset()
    for i in range(len(a) - 1):
        algo.pair_signal({"close": a[i], "hedge_close": b[i], "timestamp": i * 60})
    algo.pair_signal({"close": a[-1] - 1.0, "hedge_close": b[-1], "timestamp": 40 * 60})
    # Price crashes catastrophically past stop threshold
    sig_stop = algo.pair_signal({"close": a[-1] - 5.0, "hedge_close": b[-1], "timestamp": 41 * 60})
    assert sig_stop == "close_spread"
    assert algo._spread_position == "flat"


def test_max_holding_duration_time_stop():
    """Verify time-based exit when holding bars reaches max_holding_bars."""
    a, b = _generate_synthetic_pair(40)
    algo = PairTradingAlgorithm(
        lookback_period=20,
        entry_threshold=2.0,
        exit_threshold=0.5,
        stop_threshold=4.0,
        max_holding_bars=3,
        spread_model="cointegration",
    )
    for i in range(len(a) - 1):
        algo.pair_signal({"close": a[i], "hedge_close": b[i], "timestamp": i * 60})

    # Entry
    sig_entry = algo.pair_signal({"close": a[-1] - 1.0, "hedge_close": b[-1], "timestamp": 40 * 60})
    assert sig_entry == "long_spread"
    assert algo.state == "OPEN"

    # Bar 1: hold
    sig_b1 = algo.pair_signal({"close": a[-1] - 1.0, "hedge_close": b[-1], "timestamp": 41 * 60})
    assert sig_b1 == "hold"

    # Bar 2: hold
    sig_b2 = algo.pair_signal({"close": a[-1] - 1.0, "hedge_close": b[-1], "timestamp": 42 * 60})
    assert sig_b2 == "hold"

    # Bar 3: max_holding_bars reached -> time stop
    sig_b3 = algo.pair_signal({"close": a[-1] - 1.0, "hedge_close": b[-1], "timestamp": 43 * 60})
    assert sig_b3 == "close_spread"
    assert algo.state == "CLOSED"


def test_position_sizing_models():
    """Test equal-notional, hedge-ratio, and volatility-aware sizing models."""
    capital = 10_000.0
    close_a = 200.0
    close_b = 50.0
    hedge_ratio = 1.5

    # 1. Equal Notional
    res_eq = calculate_pair_position_sizes(
        capital=capital,
        close_a=close_a,
        close_b=close_b,
        hedge_ratio=hedge_ratio,
        sizing_model="equal_notional",
        position_fraction=0.5,
        direction="long_spread",
    )
    assert math.isclose(abs(res_eq.leg_a_notional), 2500.0)
    assert math.isclose(abs(res_eq.leg_b_notional), 2500.0)
    assert res_eq.leg_a_qty > 0  # Long A
    assert res_eq.leg_b_qty < 0  # Short B

    # 2. Hedge Ratio
    res_hr = calculate_pair_position_sizes(
        capital=capital,
        close_a=close_a,
        close_b=close_b,
        hedge_ratio=hedge_ratio,
        sizing_model="hedge_ratio",
        position_fraction=0.5,
        direction="long_spread",
    )
    # Total effective capital = 5000.0
    # notional_a = 5000 / (1 + 1.5) = 2000.0
    # notional_b = 5000 * 1.5 / (1 + 1.5) = 3000.0
    assert math.isclose(abs(res_hr.leg_a_notional), 2000.0)
    assert math.isclose(abs(res_hr.leg_b_notional), 3000.0)
    # Perfect hedge ratio means beta exposure is zero:
    assert math.isclose(res_hr.beta_exposure, 0.0, abs_tol=1e-7)

    # 3. Volatility Aware
    res_vol = calculate_pair_position_sizes(
        capital=capital,
        close_a=close_a,
        close_b=close_b,
        hedge_ratio=hedge_ratio,
        sizing_model="volatility_aware",
        position_fraction=0.5,
        spread_std=0.01,
        target_spread_risk=0.02,
        direction="short_spread",
    )
    assert res_vol.leg_a_qty < 0  # Short A
    assert res_vol.leg_b_qty > 0  # Long B
    assert res_vol.volatility_scale == 2.0  # 0.02 / 0.01 = 2.0


def test_state_machine_transitions_and_idempotency():
    """Verify all 7 states, transition rules, and duplicate entry prevention."""
    sm = PairStateManager(qualification_status="qualified")
    assert sm.state == "WATCHING"

    # Warmup
    sm.on_bar(bar_count=10, lookback_period=20)
    assert sm.state == "WATCHING"

    sm.on_bar(bar_count=20, lookback_period=20)
    assert sm.state == "QUALIFIED"

    # Trigger Entry
    assert sm.trigger_entry("long_spread") is True
    assert sm.state == "ENTRY_SIGNAL"

    # Duplicate entry attempt must be rejected (idempotency)
    assert sm.trigger_entry("long_spread") is False
    assert sm.trigger_entry("short_spread") is False

    # Confirm fill
    success, reason = sm.confirm_entry_filled(leg_a_filled=True, leg_b_filled=True)
    assert success is True
    assert sm.state == "OPEN"

    # Trigger Exit
    assert sm.trigger_exit(reason="take_profit") is True
    assert sm.state == "EXIT_SIGNAL"

    # Confirm exit
    sm.confirm_exit_filled()
    assert sm.state == "CLOSED"


def test_one_leg_execution_failure():
    """Verify legging failure handling: immediate unwind/flatten to avoid unhedged naked risk."""
    sm = PairStateManager(legging_policy="immediate_flatten")
    sm.state = "QUALIFIED"
    assert sm.trigger_entry("long_spread") is True

    # Leg A fills, but Leg B fails
    success, reason = sm.confirm_entry_filled(leg_a_filled=True, leg_b_filled=False)
    assert success is False
    assert "legging_failure_leg_b_flattened" in reason
    assert sm.state == "REJECTED"


def test_cointegration_breakdown_handling():
    """Verify that qualification loss while in position triggers exit."""
    a, b = _generate_synthetic_pair(40)
    algo = PairTradingAlgorithm(
        lookback_period=20,
        entry_threshold=2.0,
        exit_threshold=0.5,
        spread_model="cointegration",
    )
    for i in range(len(a) - 1):
        algo.pair_signal({"close": a[i], "hedge_close": b[i], "timestamp": i * 60})
    sig_entry = algo.pair_signal({"close": a[-1] - 1.0, "hedge_close": b[-1], "timestamp": 40 * 60})
    assert sig_entry == "long_spread"
    assert algo.state == "OPEN"

    # Cointegration breaks down (e.g. scanner detects structural break or pvalue exceeds threshold)
    algo.update_qualification("rejected")
    sig = algo.pair_signal({"close": a[-1] - 1.0, "hedge_close": b[-1], "timestamp": 41 * 60})
    assert sig == "close_spread"
    assert algo.state == "REJECTED"


def test_nobitex_spot_restrictions():
    """Verify Nobitex spot cannot execute market-neutral shorting and rejects invalid short requests."""
    bars_d = _make_bars([100.0 + i for i in range(50)], "BTCIRT")
    bars_h = _make_bars([50.0 + i * 0.5 for i in range(50)], "ETHIRT")
    algo = PairTradingAlgorithm(lookback_period=20, spread_model="cointegration")

    # Reject market-neutral mode on spot
    with pytest.raises(ValueError, match="Nobitex spot does not support native short selling"):
        run_pair_backtest(algo, bars_d, bars_h, mode="market_neutral")

    with pytest.raises(ValueError, match="Nobitex spot does not support native short selling"):
        run_pair_backtest(algo, bars_d, bars_h, allow_short=True)

    # Valid spot rebalance execution succeeds
    res = run_pair_backtest(algo, bars_d, bars_h, initial_cash=10_000.0)
    assert res.final_equity > 0
    assert len(res.trades) > 0


def test_hyperliquid_perpetual_compatibility_and_funding():
    """Verify Hyperliquid perp execution with signed legs, leverage, and funding adjustments."""
    bar_count = 80
    dom_closes = [100.0 + (i % 6) * 0.3 for i in range(bar_count)]
    hdg_closes = [50.0 + (i % 6) * 0.15 for i in range(bar_count)]
    # Cause divergence
    dom_closes[-15:] = [p * 0.90 for p in dom_closes[-15:]]
    dom_closes[-5:] = [p * 1.00 for p in dom_closes[-5:]]

    bars_d = _make_bars(dom_closes, "BTCUSDT")
    bars_h = _make_bars(hdg_closes, "ETHUSDT")

    algo = PairTradingAlgorithm(
        lookback_period=25,
        entry_threshold=1.5,
        exit_threshold=0.4,
        spread_model="cointegration",
        hedge_ratio=1.0,
    )

    # Mock funding rates (rate_dominant, rate_hedge)
    funding_rates = {b["timestamp"]: (0.0001, 0.00005) for b in bars_d}

    result = run_perp_pair_backtest(
        algo,
        bars_d,
        bars_h,
        initial_cash=10_000.0,
        position_fraction=0.6,
        leverage=2.0,
        funding_rates=funding_rates,
    )
    assert result.final_equity > 0
    assert len(result.trades) > 0
    assert len(result.exposure_curve) == bar_count
    assert result.sizing_model == "hedge_ratio"


def test_from_ranked_pair_factory():
    """Verify instantiating PairTradingAlgorithm directly from Pair Discovery RankedPairResult."""
    ranked = RankedPairResult(
        pair_id="hyperliquid:BTC-ETH",
        exchange="hyperliquid",
        symbol_a="BTCUSDT",
        symbol_b="ETHUSDT",
        timeframe="60",
        correlation=0.92,
        cointegration_status="stationary",
        hedge_ratio=1.234,
        intercept=-0.045,
        half_life_bars=18.5,
        liquidity_score=85.0,
        stability_score=90.0,
        pair_quality_score=88.5,
        ranking_position=1,
        qualification_status="qualified",
        cointegration_pvalue=0.008,
        adf_statistic=-3.92,
    )

    algo = PairTradingAlgorithm.from_ranked_pair(ranked)
    assert algo.symbol_a == "BTCUSDT"
    assert algo.symbol_b == "ETHUSDT"
    assert math.isclose(algo.hedge_ratio, 1.234)
    assert math.isclose(algo.intercept, -0.045)
    assert algo.qualification_status == "qualified"
    # Derived lookback from 3x half-life
    assert algo.lookback_period == max(20, int(round(18.5 * 3.0)))


def test_legacy_regression_compatibility():
    """Regression test: verify legacy Hummingbot mode functions without breaking old tests."""
    algo = PairTradingAlgorithm(
        lookback_period=30,
        entry_threshold=1.5,
        exit_threshold=0.4,
        spread_model="legacy",
    )
    assert algo.spread_model == "legacy"

    dominant = [100.0 + i * 0.05 for i in range(50)]
    hedge = [50.0 + i * 0.025 for i in range(50)]
    hedge[-5:] = [x * 1.08 for x in hedge[-5:]]  # hedge spikes -> legacy spread > 0 -> returns long_spread

    signals = [
        algo.pair_signal({"close": dominant[i], "hedge_close": hedge[i], "timestamp": i * 60})
        for i in range(50)
    ]

    # Under legacy Hummingbot logic, when hedge spikes above prediction, long_spread is triggered
    assert "long_spread" in signals
