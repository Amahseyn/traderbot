from __future__ import annotations

import pytest

from traderbot.risk.execution import (
    PairExecutionRiskManager,
    PairOrderExecutionState,
)


def test_pre_trade_depth_insufficient():
    manager = PairExecutionRiskManager(min_depth_multiple=2.0)
    # Requested notional on A: 1.0 * 60,000 = 60,000 USD
    # Requested notional on B: 20.0 * 3,000 = 60,000 USD
    # Depth on A is 150,000 (sufficient, >= 120,000)
    # Depth on B is 80,000 (< 120,000 -> insufficient!)
    allowed, reason = manager.verify_pre_trade_liquidity(
        target_qty_a=1.0,
        target_qty_b=20.0,
        quote_price_a=60_000.0,
        quote_price_b=3_000.0,
        depth_a=150_000.0,
        depth_b=80_000.0,
    )
    assert allowed is False
    assert "insufficient_order_book_depth" in reason


def test_reconciled_when_both_legs_filled():
    manager = PairExecutionRiskManager()
    state = PairOrderExecutionState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        target_qty_a=1.0,
        target_qty_b=-20.0,
        filled_qty_a=1.0,
        filled_qty_b=-20.0,
        quote_price_a=60_000.0,
        quote_price_b=3_000.0,
        avg_fill_price_a=60_050.0,
        avg_fill_price_b=2_998.0,
        status_a="FILLED",
        status_b="FILLED",
        stop_placed=True,
    )
    assessment = manager.evaluate_execution_progress(state)
    assert assessment.reconciled is True
    assert assessment.status == "RECONCILED"
    assert assessment.leg_a_fill_pct == 1.0
    assert assessment.leg_b_fill_pct == 1.0
    assert not assessment.legging_risk_warning


def test_one_leg_failure_triggers_emergency_flatten():
    manager = PairExecutionRiskManager(legging_policy="immediate_flatten")
    # Leg A filled, Leg B failed!
    state = PairOrderExecutionState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        target_qty_a=1.0,
        target_qty_b=-20.0,
        filled_qty_a=1.0,
        filled_qty_b=0.0,
        quote_price_a=60_000.0,
        quote_price_b=3_000.0,
        avg_fill_price_a=60_000.0,
        avg_fill_price_b=0.0,
        status_a="FILLED",
        status_b="FAILED",
    )
    assessment = manager.evaluate_execution_progress(state)
    assert assessment.reconciled is False
    assert assessment.status == "LEGGING_FAILURE_FLATTEN"
    assert assessment.legging_risk_warning is True
    assert any("flatten" in note.lower() for note in assessment.notes)


def test_order_timeout_treated_as_unknown_not_failed():
    manager = PairExecutionRiskManager()
    # Leg A filled, Leg B timed out
    state = PairOrderExecutionState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        target_qty_a=1.0,
        target_qty_b=-20.0,
        filled_qty_a=1.0,
        filled_qty_b=0.0,
        quote_price_a=60_000.0,
        quote_price_b=3_000.0,
        avg_fill_price_a=60_000.0,
        avg_fill_price_b=0.0,
        status_a="FILLED",
        status_b="TIMEOUT",
    )
    assessment = manager.evaluate_execution_progress(state)
    assert assessment.reconciled is False
    assert assessment.status == "UNKNOWN_ORDER_STATUS"
    assert any("timeout" in note.lower() or "unknown" in note.lower() for note in assessment.notes)


def test_partial_fill_hedge_imbalance():
    manager = PairExecutionRiskManager(max_hedge_deviation_pct=0.10)
    # Target: 1.0 BTC vs -20.0 ETH (1:20 ratio)
    # Leg A: 1.0 filled (100%)
    # Leg B: only -5.0 filled (25%!) -> ratio is 1:5, which is 75% deviation!
    state = PairOrderExecutionState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        target_qty_a=1.0,
        target_qty_b=-20.0,
        filled_qty_a=1.0,
        filled_qty_b=-5.0,
        quote_price_a=60_000.0,
        quote_price_b=3_000.0,
        avg_fill_price_a=60_000.0,
        avg_fill_price_b=3_000.0,
        status_a="FILLED",
        status_b="PARTIALLY_FILLED",
        target_hedge_ratio=1.0,  # Equal notional target (60k vs 60k)
    )
    assessment = manager.evaluate_execution_progress(state)
    assert assessment.reconciled is False
    assert assessment.status == "PARTIAL_FILL_HEDGE_IMBALANCE"
    assert assessment.legging_risk_warning is True


def test_failed_stop_placement_triggers_flatten():
    manager = PairExecutionRiskManager()
    state = PairOrderExecutionState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        target_qty_a=1.0,
        target_qty_b=-20.0,
        filled_qty_a=1.0,
        filled_qty_b=-20.0,
        quote_price_a=60_000.0,
        quote_price_b=3_000.0,
        avg_fill_price_a=60_000.0,
        avg_fill_price_b=3_000.0,
        status_a="FILLED",
        status_b="FILLED",
        stop_placed=False,
        stop_placement_failed=True,
    )
    assessment = manager.evaluate_execution_progress(state)
    assert assessment.reconciled is False
    assert assessment.status == "STOP_PLACEMENT_FAILED_FLATTEN"
    assert any("stop" in note.lower() for note in assessment.notes)


def test_excessive_slippage():
    manager = PairExecutionRiskManager(max_slippage_pct=0.005)
    # Leg A filled at 60,600 vs quote 60,000 (1.0% slippage > 0.5% limit!)
    state = PairOrderExecutionState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        target_qty_a=1.0,
        target_qty_b=-20.0,
        filled_qty_a=1.0,
        filled_qty_b=-20.0,
        quote_price_a=60_000.0,
        quote_price_b=3_000.0,
        avg_fill_price_a=60_600.0,
        avg_fill_price_b=3_000.0,
        status_a="FILLED",
        status_b="FILLED",
        stop_placed=True,
    )
    assessment = manager.evaluate_execution_progress(state)
    assert any("slippage" in note.lower() for note in assessment.notes)

