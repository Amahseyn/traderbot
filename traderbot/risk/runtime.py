from __future__ import annotations

from traderbot.risk.manager import RiskLimits, RiskManager
from traderbot.risk.portfolio import PortfolioRiskLimits, PortfolioRiskManager

_managers: dict[str, RiskManager] = {}
_portfolio_manager: PortfolioRiskManager | None = None


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


def get_portfolio_risk_manager() -> PortfolioRiskManager:
    global _portfolio_manager
    if _portfolio_manager is None:
        _portfolio_manager = PortfolioRiskManager()
    return _portfolio_manager


def configure_portfolio_risk_manager(limits: PortfolioRiskLimits) -> PortfolioRiskManager:
    global _portfolio_manager
    _portfolio_manager = PortfolioRiskManager(limits)
    return _portfolio_manager


def clear_portfolio_risk_manager() -> None:
    global _portfolio_manager
    _portfolio_manager = None


def clear_risk_managers() -> None:
    _managers.clear()
    clear_portfolio_risk_manager()
