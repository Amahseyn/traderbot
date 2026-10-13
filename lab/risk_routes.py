from __future__ import annotations

from typing import Any

from traderbot.risk.manager import RiskLimits
from traderbot.risk.runtime import configure_risk_manager, get_risk_manager
from traderbot.risk.validation import validate_risk_limits


def _risk_scope(body: dict[str, Any] | None) -> str:
    if not body:
        return "lab"
    scope = str(body.get("scope") or "lab").strip()
    return scope or "lab"


def register_risk_routes(app) -> None:
    from fastapi import HTTPException, Query

    @app.get("/api/risk/state")
    def api_risk_state(scope: str = Query(default="lab")) -> dict[str, Any]:
        return get_risk_manager(scope).snapshot()

    @app.post("/api/risk/kill-switch")
    def api_risk_kill_switch(body: dict[str, Any]) -> dict[str, Any]:
        enabled = bool(body.get("enabled"))
        manager = get_risk_manager(_risk_scope(body))
        manager.limits.kill_switch = enabled
        return manager.snapshot()

    @app.post("/api/risk/limits")
    def api_risk_limits(body: dict[str, Any]) -> dict[str, Any]:
        scope = _risk_scope(body)
        current = get_risk_manager(scope)
        try:
            limits = RiskLimits(
                capital_cap=float(body.get("capital_cap", current.limits.capital_cap)),
                daily_loss_limit_pct=float(
                    body.get("daily_loss_limit_pct", current.limits.daily_loss_limit_pct),
                ),
                max_drawdown_pct=float(
                    body.get("max_drawdown_pct", current.limits.max_drawdown_pct),
                ),
                volatility_target_pct=float(
                    body.get("volatility_target_pct", current.limits.volatility_target_pct),
                ),
                kill_switch=bool(body.get("kill_switch", current.limits.kill_switch)),
                stop_loss_pct=body.get("stop_loss_pct", current.limits.stop_loss_pct),
            )
            validate_risk_limits(limits)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        manager = configure_risk_manager(limits, scope=scope)
        return manager.snapshot()
