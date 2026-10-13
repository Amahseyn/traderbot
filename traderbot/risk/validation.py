from __future__ import annotations

from traderbot.risk.manager import RiskLimits


def validate_risk_limits(limits: RiskLimits) -> None:
    if limits.capital_cap <= 0:
        raise ValueError("capital_cap must be positive")
    if limits.daily_loss_limit_pct <= 0 or limits.daily_loss_limit_pct > 100:
        raise ValueError("daily_loss_limit_pct must be in (0, 100]")
    if limits.max_drawdown_pct <= 0 or limits.max_drawdown_pct > 100:
        raise ValueError("max_drawdown_pct must be in (0, 100]")
    if limits.volatility_target_pct <= 0:
        raise ValueError("volatility_target_pct must be positive")
    if limits.atr_lookback < 1:
        raise ValueError("atr_lookback must be >= 1")
    if limits.stop_loss_pct is not None:
        if limits.stop_loss_pct <= 0 or limits.stop_loss_pct >= 100:
            raise ValueError("stop_loss_pct must be in (0, 100) when set")
