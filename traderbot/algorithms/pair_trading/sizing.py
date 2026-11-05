from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

PairSizingModel = Literal["equal_notional", "hedge_ratio", "volatility_aware"]


@dataclass(frozen=True, slots=True)
class PairSizingResult:
    leg_a_qty: float
    leg_b_qty: float
    leg_a_notional: float
    leg_b_notional: float
    gross_notional: float
    net_notional: float
    beta_exposure: float
    residual_market_exposure: float
    sizing_model: PairSizingModel
    volatility_scale: float = 1.0


def calculate_pair_position_sizes(
    *,
    capital: float,
    close_a: float,
    close_b: float,
    hedge_ratio: float = 1.0,
    sizing_model: PairSizingModel = "hedge_ratio",
    position_fraction: float = 0.5,
    spread_std: float | None = None,
    target_spread_risk: float = 0.02,
    min_vol_scale: float = 0.20,
    max_vol_scale: float = 2.50,
    leverage: float = 1.0,
    direction: Literal["long_spread", "short_spread"] = "long_spread",
) -> PairSizingResult:
    """
    Calculate pair quantities and exposure metrics for Leg A and Leg B.

    Supported sizing models:
      - 'equal_notional': 50/50 capital split between Leg A and Leg B.
      - 'hedge_ratio': Allocates capital proportional to (1 / (1 + beta)) and (beta / (1 + beta)),
                       achieving spread-neutral dollar sensitivity.
      - 'volatility_aware': Scales capital inversely with rolling spread standard deviation,
                            clamped by [min_vol_scale, max_vol_scale], then applies hedge ratio.

    Direction:
      - 'long_spread': Long Leg A (+), Short Leg B (-)
      - 'short_spread': Short Leg A (-), Long Leg B (+)
    """
    if capital <= 0:
        raise ValueError("capital must be positive")
    if close_a <= 0 or close_b <= 0:
        raise ValueError("prices must be positive")
    if hedge_ratio <= 0:
        raise ValueError("hedge_ratio must be positive")
    if not 0 < position_fraction <= 1.0:
        raise ValueError("position_fraction must be in (0, 1]")
    if leverage < 1.0:
        raise ValueError("leverage must be >= 1.0")

    effective_capital = capital * position_fraction * leverage
    vol_scale = 1.0

    if sizing_model == "equal_notional":
        notional_a = effective_capital / 2.0
        notional_b = effective_capital / 2.0
    elif sizing_model == "hedge_ratio":
        notional_a = effective_capital / (1.0 + hedge_ratio)
        notional_b = (effective_capital * hedge_ratio) / (1.0 + hedge_ratio)
    elif sizing_model == "volatility_aware":
        if spread_std is not None and spread_std > 1e-12:
            raw_scale = target_spread_risk / spread_std
            vol_scale = max(min_vol_scale, min(max_vol_scale, raw_scale))
        else:
            vol_scale = 1.0
        scaled_capital = effective_capital * vol_scale
        notional_a = scaled_capital / (1.0 + hedge_ratio)
        notional_b = (scaled_capital * hedge_ratio) / (1.0 + hedge_ratio)
    else:
        raise ValueError(f"unsupported sizing_model: {sizing_model!r}")

    qty_a_abs = notional_a / close_a
    qty_b_abs = notional_b / close_b

    if direction == "long_spread":
        leg_a_qty = qty_a_abs
        leg_b_qty = -qty_b_abs
    elif direction == "short_spread":
        leg_a_qty = -qty_a_abs
        leg_b_qty = qty_b_abs
    else:
        raise ValueError(f"unsupported direction: {direction!r}")

    signed_notional_a = leg_a_qty * close_a
    signed_notional_b = leg_b_qty * close_b

    gross_notional = abs(signed_notional_a) + abs(signed_notional_b)
    net_notional = signed_notional_a + signed_notional_b

    # Beta-weighted residual dollar exposure: (Notional_A + Notional_B / beta)
    # Under perfect hedge-ratio sizing, signed_notional_a = - signed_notional_b / beta, yielding 0.0
    beta_exposure = signed_notional_a + (signed_notional_b / hedge_ratio)
    residual_market_exposure = net_notional / gross_notional if gross_notional > 0 else 0.0

    return PairSizingResult(
        leg_a_qty=leg_a_qty,
        leg_b_qty=leg_b_qty,
        leg_a_notional=signed_notional_a,
        leg_b_notional=signed_notional_b,
        gross_notional=gross_notional,
        net_notional=net_notional,
        beta_exposure=beta_exposure,
        residual_market_exposure=residual_market_exposure,
        sizing_model=sizing_model,
        volatility_scale=vol_scale,
    )

