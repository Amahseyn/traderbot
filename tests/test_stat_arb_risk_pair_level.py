from __future__ import annotations

import pytest

from traderbot.risk.manager import RiskLimits, RiskManager
from traderbot.risk.pair_models import PairRiskLimits, PairRiskState, StatArbRiskVerdict


def _make_manager(pair_limits: PairRiskLimits | None = None) -> RiskManager:
    limits = RiskLimits(
        capital_cap=100_000.0,
        daily_loss_limit_pct=5.0,
        max_drawdown_pct=15.0,
        pair_limits=pair_limits or PairRiskLimits(),
    )
    rm = RiskManager(limits)
    rm.reset_session(100_000.0)
    return rm


def test_pair_risk_allocation_limit():
    rm = _make_manager(PairRiskLimits(max_pair_allocation_pct=0.20))  # Max 20% of 100k = 20k
    # Pair gross = 25,000 USD (exceeds 20,000 limit)
    state = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.25,
        leg_b_qty=-4.0,
        current_price_a=50_000.0,  # 12,500
        current_price_b=3_125.0,   # 12,500 -> Gross = 25,000
        allocated_capital=20_000.0,
    )
    verdict = rm.evaluate_pair_limits(state, total_equity=100_000.0)
    assert not verdict.allowed
    assert "max_pair_allocation_exceeded" in verdict.reason


def test_pair_risk_gross_exposure_limit():
    rm = _make_manager(PairRiskLimits(max_gross_pair_exposure=50_000.0))
    # Pair gross = 60,000 USD (exceeds 50k absolute ceiling)
    state = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.5,
        leg_b_qty=-10.0,
        current_price_a=60_000.0,  # 30,000
        current_price_b=3_000.0,   # 30,000 -> Gross = 60,000
        allocated_capital=60_000.0,
    )
    verdict = rm.evaluate_pair_limits(state, total_equity=500_000.0)
    assert not verdict.allowed
    assert "max_gross_pair_exposure_exceeded" in verdict.reason


def test_pair_risk_net_exposure_limit():
    rm = _make_manager(PairRiskLimits(max_net_exposure_pct=0.15))
    # Leg A: 20,000 USD Long
    # Leg B: 10,000 USD Short
    # Gross = 30,000. Net = +10,000. Net / Gross = 33.3% > 15%!
    state = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.4,
        leg_b_qty=-3.3333,
        current_price_a=50_000.0,  # +20,000
        current_price_b=3_000.0,   # -10,000
        allocated_capital=30_000.0,
    )
    verdict = rm.evaluate_pair_limits(state, total_equity=200_000.0)
    assert not verdict.allowed
    assert "max_net_exposure_exceeded" in verdict.reason


def test_pair_risk_leverage_limit():
    rm = _make_manager(PairRiskLimits(max_leverage=3.0))
    # Allocated capital: 5,000 USD
    # Gross notional: 20,000 USD -> Leverage = 4.0x > 3.0x max!
    state = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.2,
        leg_b_qty=-3.3333,
        current_price_a=50_000.0,  # 10,000
        current_price_b=3_000.0,   # 10,000 -> Gross = 20,000
        allocated_capital=5_000.0,
    )
    verdict = rm.evaluate_pair_limits(state, total_equity=100_000.0)
    assert not verdict.allowed
    assert "max_leverage_exceeded" in verdict.reason


def test_pair_risk_hedge_deviation_limit():
    rm = _make_manager(PairRiskLimits(max_hedge_deviation_pct=0.10))
    # Target hedge ratio = 1.0 (equal notional)
    # Leg A = 8,000 USD. Leg B = 10,000 USD (gross = 18,000 <= 20,000 allocation; ratio = 1.25 -> 25% deviation > 10% limit)
    state = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.16,
        leg_b_qty=-3.33333,
        current_price_a=50_000.0,  # 8,000
        current_price_b=3_000.0,   # 10,000
        hedge_ratio=1.0,
        allocated_capital=20_000.0,
    )
    verdict = rm.evaluate_pair_limits(state, total_equity=100_000.0)
    assert not verdict.allowed
    assert "max_hedge_deviation_exceeded" in verdict.reason


def test_pair_risk_holding_duration_stop():
    rm = _make_manager(PairRiskLimits(max_holding_duration_bars=120))
    state = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.1,
        leg_b_qty=-1.6666,
        current_price_a=50_000.0,
        current_price_b=3_000.0,
        allocated_capital=10_000.0,
        holding_bars=125,  # Exceeded 120 bars!
    )
    verdict = rm.evaluate_pair_limits(state, total_equity=100_000.0)
    assert not verdict.allowed
    assert "max_holding_duration_exceeded" in verdict.reason


def test_pair_risk_loss_stop():
    rm = _make_manager(PairRiskLimits(max_pair_loss_pct=3.0))
    # Allocated capital = 10,000 USD
    # Unrealized loss = -350 USD (3.5% loss > 3.0% stop!)
    state = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.1,
        leg_b_qty=-1.6666,
        current_price_a=50_000.0,
        current_price_b=3_000.0,
        allocated_capital=10_000.0,
        unrealized_pnl=-350.0,
    )
    verdict = rm.evaluate_pair_limits(state, total_equity=100_000.0)
    assert not verdict.allowed
    assert "max_pair_loss_exceeded" in verdict.reason
    assert "BTC-ETH" in rm.pair_emergency_exits


def test_pair_risk_spread_divergence_stop():
    rm = _make_manager(PairRiskLimits(max_spread_divergence_z=4.0))
    # Z-score diverged to 4.5!
    state = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.1,
        leg_b_qty=-1.6666,
        current_price_a=50_000.0,
        current_price_b=3_000.0,
        allocated_capital=10_000.0,
        current_z_score=4.5,
    )
    verdict = rm.evaluate_pair_limits(state, total_equity=100_000.0)
    assert not verdict.allowed
    assert "max_spread_divergence_exceeded" in verdict.reason
    assert "BTC-ETH" in rm.pair_emergency_exits


def test_pair_risk_reducing_order_exemption_during_halt():
    rm = _make_manager(PairRiskLimits())
    # Manually trigger pair emergency exit
    rm.trigger_pair_emergency_exit("BTC-ETH", operator="risk_bot", reason="stop_triggered")
    assert "BTC-ETH" in rm.pair_emergency_exits

    # New risk-increasing order is BLOCKED
    state = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.1,
        leg_b_qty=-1.6666,
        current_price_a=50_000.0,
        current_price_b=3_000.0,
        allocated_capital=10_000.0,
    )
    verdict_entry = rm.evaluate_pair_order(
        pair_id="BTC-ETH",
        action="long_spread",
        pair_state=state,
        total_equity=100_000.0,
        is_risk_reducing=False,
    )
    assert not verdict_entry.allowed

    # Risk-reducing exit order is PERMITTED
    verdict_exit = rm.evaluate_pair_order(
        pair_id="BTC-ETH",
        action="close_spread",
        pair_state=state,
        total_equity=100_000.0,
        is_risk_reducing=True,
    )
    assert verdict_exit.allowed is True


def test_audited_pair_emergency_exit_and_clear():
    rm = _make_manager(PairRiskLimits())
    rm.trigger_pair_emergency_exit("BTC-ETH", operator="alice", reason="manual_circuit_breaker")
    assert len(rm.audit_log) == 1
    assert rm.audit_log[0]["action"] == "pair_emergency_halt"
    assert rm.audit_log[0]["operator"] == "alice"

    rm.clear_pair_emergency_exit("BTC-ETH", operator="bob", reason="positions_reconciled")
    assert "BTC-ETH" not in rm.pair_emergency_exits
    assert len(rm.audit_log) == 2
    assert rm.audit_log[1]["action"] == "pair_unhalt"
    assert rm.audit_log[1]["operator"] == "bob"
