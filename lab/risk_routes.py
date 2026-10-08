from __future__ import annotations

from typing import Any

from traderbot.risk.manager import RiskLimits
from traderbot.risk.runtime import configure_risk_manager, get_risk_manager


def register_risk_routes(app) -> None:
    from fastapi import HTTPException

    @app.get("/api/risk/state")
    def api_risk_state() -> dict[str, Any]:
        return get_risk_manager().snapshot()

    @app.post("/api/risk/kill-switch")
    def api_risk_kill_switch(body: dict[str, Any]) -> dict[str, Any]:
        enabled = bool(body.get("enabled"))
        manager = get_risk_manager()
        manager.limits.kill_switch = enabled
        return manager.snapshot()

    @app.post("/api/risk/limits")
    def api_risk_limits(body: dict[str, Any]) -> dict[str, Any]:
        try:
            limits = RiskLimits(
                capital_cap=float(body.get("capital_cap", get_risk_manager().limits.capital_cap)),
                daily_loss_limit_pct=float(
                    body.get("daily_loss_limit_pct", get_risk_manager().limits.daily_loss_limit_pct),
                ),
                max_drawdown_pct=float(
                    body.get("max_drawdown_pct", get_risk_manager().limits.max_drawdown_pct),
                ),
                volatility_target_pct=float(
                    body.get("volatility_target_pct", get_risk_manager().limits.volatility_target_pct),
                ),
                kill_switch=bool(body.get("kill_switch", get_risk_manager().limits.kill_switch)),
                stop_loss_pct=body.get("stop_loss_pct", get_risk_manager().limits.stop_loss_pct),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        manager = configure_risk_manager(limits)
        return manager.snapshot()
