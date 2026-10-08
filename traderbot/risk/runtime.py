from __future__ import annotations

from traderbot.risk.manager import RiskLimits, RiskManager

_runtime: RiskManager | None = None


def get_risk_manager() -> RiskManager:
    global _runtime
    if _runtime is None:
        _runtime = RiskManager(RiskLimits())
    return _runtime


def configure_risk_manager(limits: RiskLimits) -> RiskManager:
    global _runtime
    _runtime = RiskManager(limits)
    return _runtime
