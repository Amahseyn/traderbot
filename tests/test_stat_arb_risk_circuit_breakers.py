from __future__ import annotations

import pytest

from traderbot.risk.pair_models import PairRiskLimits, PairRiskState
from traderbot.risk.portfolio import PortfolioRiskLimits, PortfolioRiskManager


def test_portfolio_circuit_breaker_daily_loss_halts():
    pm = PortfolioRiskManager(PortfolioRiskLimits(portfolio_daily_loss_limit_pct=5.0))
    pm.reset_session(100_000.0)

    # Initial entry is allowed
    verdict1 = pm.evaluate_pair_entry(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        notional_a=10_000.0,
        notional_b=10_000.0,
        total_equity=100_000.0,
    )
    assert verdict1.allowed is True

    # Equity plunges 6% to 94,000 USD -> Breaches 5% daily loss limit!
    verdict2 = pm.evaluate_pair_entry(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        notional_a=10_000.0,
        notional_b=10_000.0,
        total_equity=94_000.0,
    )
    assert verdict2.allowed is False
    assert pm.halted is True
    assert verdict2.reason == "portfolio_daily_loss_limit"

    # Risk-reducing close orders remain permitted!
    verdict_exit = pm.evaluate_pair_order(
        pair_id="BTC-ETH",
        action="close_spread",
        notional_a=10_000.0,
        notional_b=10_000.0,
        total_equity=94_000.0,
        is_risk_reducing=True,
    )
    assert verdict_exit.allowed is True


def test_portfolio_circuit_breaker_max_drawdown():
    pm = PortfolioRiskManager(PortfolioRiskLimits(portfolio_max_drawdown_pct=15.0))
    pm.reset_session(100_000.0)
    # Peak equity reaches 120,000
    pm.update_mark(120_000.0)
    assert pm.peak_equity == 120_000.0

    # Equity drops to 100,000 (-16.6% drawdown from peak 120k > 15% limit!)
    verdict = pm.evaluate_pair_entry(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        notional_a=5_000.0,
        notional_b=5_000.0,
        total_equity=100_000.0,
    )
    assert verdict.allowed is False
    assert pm.halted is True
    assert verdict.reason == "portfolio_max_drawdown"


def test_portfolio_max_concurrent_pairs_limit():
    pm = PortfolioRiskManager(PortfolioRiskLimits(max_concurrent_pairs=2))
    pm.reset_session(100_000.0)

    # Register pair 1
    pm.register_pair(PairRiskState(pair_id="BTC-ETH", symbol_a="BTC", symbol_b="ETH"))
    # Register pair 2
    pm.register_pair(PairRiskState(pair_id="SOL-AVAX", symbol_a="SOL", symbol_b="AVAX"))

    # Attempting pair 3 breaches limit
    verdict = pm.evaluate_pair_entry(
        pair_id="NEAR-DOT",
        symbol_a="NEAR",
        symbol_b="DOT",
        notional_a=5_000.0,
        notional_b=5_000.0,
        total_equity=100_000.0,
    )
    assert verdict.allowed is False
    assert "max_concurrent_pairs_reached" in verdict.reason


def test_audited_portfolio_kill_switch_and_unhalt():
    pm = PortfolioRiskManager()
    pm.reset_session(100_000.0)

    # Trigger kill switch
    pm.trigger_kill_switch(operator="chief_risk_officer", reason="Extreme market disclocation")
    assert pm.halted is True
    assert pm.limits.kill_switch is True
    assert len(pm.audit_log) == 1
    assert pm.audit_log[0]["action"] == "portfolio_kill_switch"
    assert pm.audit_log[0]["operator"] == "chief_risk_officer"

    # Evaluates to rejected
    verdict = pm.evaluate_pair_entry(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        notional_a=1_000.0,
        notional_b=1_000.0,
        total_equity=100_000.0,
    )
    assert verdict.allowed is False

    # Audited unhalt
    pm.unhalt(operator="compliance_head", reason="Market stabilized and books reconciled")
    assert pm.halted is False
    assert pm.limits.kill_switch is False
    assert len(pm.audit_log) == 2
    assert pm.audit_log[1]["action"] == "portfolio_unhalt"
    assert pm.audit_log[1]["operator"] == "compliance_head"


def test_portfolio_restart_recovery_and_persistence(tmp_path):
    pm = PortfolioRiskManager(PortfolioRiskLimits(max_concurrent_pairs=3))
    pm.reset_session(50_000.0)
    pm.update_mark(55_000.0)
    pair = PairRiskState(
        pair_id="BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=0.1,
        leg_b_qty=-1.5,
        current_price_a=60_000.0,
        current_price_b=3_000.0,
    )
    pm.register_pair(pair, spread_history=[0.01, 0.02, 0.03])
    pm.trigger_kill_switch(operator="system_bot", reason="test_halt")

    # Persist to disk
    state_file = tmp_path / "portfolio_risk.json"
    pm.save_to_file(state_file)

    # Fresh instance reload
    pm2 = PortfolioRiskManager()
    loaded = pm2.load_from_file(state_file)
    assert loaded is True
    assert pm2.peak_equity == 55_000.0
    assert pm2.halted is True
    assert "BTC-ETH" in pm2.active_pairs
    assert pm2.active_pairs["BTC-ETH"].symbol_a == "BTC"
    assert len(pm2.audit_log) == 1
    assert pm2.audit_log[0]["operator"] == "system_bot"

