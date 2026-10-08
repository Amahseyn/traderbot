from traderbot.risk.manager import RiskLimits, RiskManager


def test_risk_kill_switch_blocks_orders():
    manager = RiskManager(RiskLimits(kill_switch=True))
    verdict = manager.evaluate("buy", equity=1000.0, mark_price=100.0)
    assert not verdict.allowed
    assert verdict.reason == "kill_switch"


def test_risk_daily_loss_halts():
    manager = RiskManager(RiskLimits(daily_loss_limit_pct=5.0))
    manager.reset_session(1000.0)
    verdict = manager.evaluate("buy", equity=940.0, mark_price=10.0)
    assert not verdict.allowed
    assert manager.halted
