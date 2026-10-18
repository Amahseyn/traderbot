from __future__ import annotations

import os

from traderbot.markets.execution_costs import (
    HYPERLIQUID_PERP_TAKER_FEE,
    execution_cost_profile,
)

# Default backtest costs match Hyperliquid perp tier-0 taker (market-style fills).
_DEFAULT_FEE = HYPERLIQUID_PERP_TAKER_FEE
# No extra slippage model by default (Hyperliquid); Nobitex uses execution_cost_profile slippage.
_DEFAULT_SLIPPAGE = 0.0


def _rate_from_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return float(raw)


DEFAULT_TRADE_FEE_RATE = _rate_from_env("TRADERBOT_DEFAULT_FEE_RATE", _DEFAULT_FEE)
DEFAULT_SLIPPAGE_RATE = _rate_from_env("TRADERBOT_DEFAULT_SLIPPAGE_RATE", _DEFAULT_SLIPPAGE)
DEFAULT_BACKTEST_EXECUTION = "next_open"


def backtest_cost_rates(
    exchange: str | None = None,
    *,
    fee_role: str = "taker",
    market_kind: str = "perp",
) -> tuple[float, float]:
    """Return (fee_rate, slippage_rate) for a venue; falls back to global defaults."""
    if exchange is None:
        return DEFAULT_TRADE_FEE_RATE, DEFAULT_SLIPPAGE_RATE
    role = "maker" if fee_role == "maker" else "taker"
    kind = "spot" if market_kind == "spot" else "perp"
    profile = execution_cost_profile(exchange, fee_role=role, market_kind=kind)  # type: ignore[arg-type]
    return profile.fee_rate, profile.slippage_rate
