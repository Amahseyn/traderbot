from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from traderbot.markets.exchange import LIVE_EXCHANGES, normalize_live_exchange

FeeRole = Literal["taker", "maker"]

# Official Hyperliquid fee tiers (tier 0, no staking/referral discounts):
# https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees
# Perps: taker 0.045%, maker 0.015%. Spot: taker 0.070%, maker 0.040%.
HYPERLIQUID_PERP_TAKER_FEE = 0.00045
HYPERLIQUID_PERP_MAKER_FEE = 0.00015
HYPERLIQUID_SPOT_TAKER_FEE = 0.0007
HYPERLIQUID_SPOT_MAKER_FEE = 0.0004
# Perp fills on Hyperliquid are against the book; we do not model extra slippage by default.
HYPERLIQUID_SLIPPAGE = 0.0

# Nobitex retail spot (approximate; verify on nobitex.ir for your VIP tier).
_NOBITEX_TAKER = 0.0035
_NOBITEX_MAKER = 0.0025
_NOBITEX_SLIPPAGE = 0.001


@dataclass(frozen=True, slots=True)
class ExecutionCostProfile:
    exchange: str
    fee_role: FeeRole
    fee_rate: float
    slippage_rate: float
    label: str


def execution_cost_profile(
    exchange: str,
    *,
    fee_role: FeeRole = "taker",
    market_kind: Literal["perp", "spot"] = "perp",
) -> ExecutionCostProfile:
    venue = normalize_live_exchange(exchange)
    if venue == "hyperliquid":
        if market_kind == "spot":
            fee = HYPERLIQUID_SPOT_MAKER_FEE if fee_role == "maker" else HYPERLIQUID_SPOT_TAKER_FEE
            label = f"Hyperliquid spot {fee_role}"
        else:
            fee = HYPERLIQUID_PERP_MAKER_FEE if fee_role == "maker" else HYPERLIQUID_PERP_TAKER_FEE
            label = f"Hyperliquid perp {fee_role}"
        return ExecutionCostProfile(
            exchange=venue,
            fee_role=fee_role,
            fee_rate=fee,
            slippage_rate=HYPERLIQUID_SLIPPAGE,
            label=label,
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
