from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from traderbot.markets.exchange import LIVE_EXCHANGES, normalize_live_exchange

FeeRole = Literal["taker", "maker"]


@dataclass(frozen=True, slots=True)
class ExecutionCostProfile:
    exchange: str
    fee_role: FeeRole
    fee_rate: float
    slippage_rate: float
    label: str


# Nobitex retail taker (spot); maker often similar without VIP — override via env in trading_costs.
_NOBITEX_TAKER = 0.0035
_NOBITEX_MAKER = 0.0025
_NOBITEX_SLIPPAGE = 0.001

# Hyperliquid base tier (see docs / Hummingbot hyperliquid connector); maker rebates lower effective cost.
_HYPERLIQUID_TAKER = 0.00045
_HYPERLIQUID_MAKER = 0.00015
_HYPERLIQUID_SLIPPAGE = 0.0005


def execution_cost_profile(exchange: str, *, fee_role: FeeRole = "taker") -> ExecutionCostProfile:
    venue = normalize_live_exchange(exchange)
    if venue == "hyperliquid":
        fee = _HYPERLIQUID_MAKER if fee_role == "maker" else _HYPERLIQUID_TAKER
        return ExecutionCostProfile(
            exchange=venue,
            fee_role=fee_role,
            fee_rate=fee,
            slippage_rate=_HYPERLIQUID_SLIPPAGE,
            label=f"Hyperliquid {fee_role}",
        )
    fee = _NOBITEX_MAKER if fee_role == "maker" else _NOBITEX_TAKER
    return ExecutionCostProfile(
        exchange=venue,
        fee_role=fee_role,
        fee_rate=fee,
        slippage_rate=_NOBITEX_SLIPPAGE,
        label=f"Nobitex {fee_role}",
    )


def list_supported_exchanges() -> tuple[str, ...]:
    return LIVE_EXCHANGES
