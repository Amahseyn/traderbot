from __future__ import annotations

from traderbot.risk.manager import RiskLimits, RiskManager

_managers: dict[str, RiskManager] = {}


def _normalize_scope(scope: str | None) -> str:
    cleaned = (scope or "default").strip()
    return cleaned or "default"


def get_risk_manager(scope: str | None = None) -> RiskManager:
    key = _normalize_scope(scope)
    manager = _managers.get(key)
    if manager is None:
        manager = RiskManager(RiskLimits())
        _managers[key] = manager
    return manager


def configure_risk_manager(limits: RiskLimits, scope: str | None = None) -> RiskManager:
    key = _normalize_scope(scope)
    manager = RiskManager(limits)
    _managers[key] = manager
    return manager


def clear_risk_managers() -> None:
    _managers.clear()
