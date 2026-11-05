from __future__ import annotations

import pytest
from traderbot.risk.manager import RiskLimits, RiskManager


def test_audited_kill_switch_and_unhalt() -> None:
    rm = RiskManager(limits=RiskLimits(daily_loss_limit_pct=5.0, max_drawdown_pct=10.0))
    rm.reset_session(10_000.0)

    # Trigger manual kill switch
    rm.trigger_kill_switch(operator="risk_officer_alice", reason="API instability observed on exchange")
    assert rm.halted is True
    assert rm.limits.kill_switch is True
    assert rm.halt_reason == "API instability observed on exchange"

    # Evaluation must reject new buy orders
    verdict = rm.evaluate("buy", equity=10_000.0, mark_price=100.0)
    assert verdict.allowed is False
    assert verdict.reason in ("kill_switch", "API instability observed on exchange")

    # Sells (risk reductions) are still allowed during a halt
    sell_verdict = rm.evaluate("sell", equity=10_000.0, mark_price=100.0)
    assert sell_verdict.allowed is True

    # Audit log must contain the halt event
    assert len(rm.audit_log) == 1
    assert rm.audit_log[0]["operator"] == "risk_officer_alice"
    assert rm.audit_log[0]["action"] == "halt"

    # Operator unhalts
    rm.unhalt(operator="risk_officer_bob", reason="API connections re-established and healthy")
    assert rm.halted is False
    assert rm.limits.kill_switch is False
    assert rm.halt_reason == ""

    # Audit log must contain both events
    assert len(rm.audit_log) == 2
    assert rm.audit_log[1]["operator"] == "risk_officer_bob"
    assert rm.audit_log[1]["action"] == "unhalt"

    # Subsequent buy order is allowed
    verdict_after = rm.evaluate("buy", equity=10_000.0, mark_price=100.0)
    assert verdict_after.allowed is True


def test_snapshot_preserves_audit_log() -> None:
    rm = RiskManager(limits=RiskLimits(max_drawdown_pct=10.0))
    rm.reset_session(100.0)
    rm.trigger_kill_switch(operator="compliance_bot", reason="Emergency volatility halt")

    snap = rm.snapshot()
    assert "audit_log" in snap
    assert len(snap["audit_log"]) == 1

    rm2 = RiskManager(limits=RiskLimits(max_drawdown_pct=10.0))
    rm2.restore_from_snapshot(snap)
    assert rm2.halted is True
    assert len(rm2.audit_log) == 1
    assert rm2.audit_log[0]["operator"] == "compliance_bot"

