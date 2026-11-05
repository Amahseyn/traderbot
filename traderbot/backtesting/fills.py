"""Bar-level fill model shared by the backtest engine and the paper trader.

All checks use only the bar *after* an order was placed, so there is no look-ahead:

* Resting limit (maker) orders fill only when the bar trades **through** the price
  (buy: ``low < limit``, sell: ``high > limit``) and fill **at the limit price**.
* Stops are taker fills at the stop price, or the bar open when the bar gaps through it.
* Take-profits are resting reduce-only limits: maker fill at the target price.
* When a stop and a take-profit both sit inside one bar, the stop wins (conservative).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

Side = Literal["buy", "sell"]


def calculate_market_impact(
    price: float,
    qty: float,
    volume: float | None = None,
    volatility: float | None = None,
    gamma: float = 0.1,
) -> float:
    """Square-root market impact per execution-realistic-simulation skill.

    I(Q) = gamma * sigma * sqrt(Q / V) * P_mid.
    """
    if price <= 0 or qty <= 0:
        return 0.0
    if volume is None or volume <= 0 or volatility is None or volatility <= 0:
        return 0.0
    participation = qty / volume
    participation = min(1.0, max(0.0, participation))
    return float(gamma * volatility * math.sqrt(participation) * price)


def simulated_fill_price(
    side: Side,
    mid_price: float,
    *,
    qty: float = 0.0,
    volume: float | None = None,
    volatility: float | None = None,
    spread_pct: float = 0.0,
    slippage_rate: float = 0.0,
    is_maker: bool = False,
    gamma: float = 0.1,
) -> float:
    """Calculate realistic executable fill price incorporating spread crossing, impact, and slippage."""
    if mid_price <= 0:
        raise ValueError("mid_price must be positive")
    if is_maker:
        return mid_price

    half_spread = max(0.0, spread_pct) / 2.0
    impact = calculate_market_impact(mid_price, qty, volume, volatility, gamma=gamma)
    impact_pct = impact / mid_price if mid_price > 0 else 0.0

    total_frictions = half_spread + slippage_rate + impact_pct
    if side == "buy":
        return mid_price * (1.0 + total_frictions)
    return mid_price * (1.0 - total_frictions)



def limit_fill_price(
    side: str,
    limit_price: float,
    bar: dict[str, Any],
    *,
    penetration_pct: float = 0.0,
) -> float | None:
    low = float(bar.get("low", bar["close"]))
    high = float(bar.get("high", bar["close"]))
    buy_threshold = limit_price * (1.0 - abs(penetration_pct))
    sell_threshold = limit_price * (1.0 + abs(penetration_pct))
    if side == "buy" and low < buy_threshold:
        return limit_price
    if side == "sell" and high > sell_threshold:
        return limit_price
    return None


def post_only_accepts(side: str, limit_price: float, reference_price: float) -> bool:
    """A post-only buy must sit below the market, a post-only sell above it."""
    if side == "buy":
        return limit_price < reference_price
    return limit_price > reference_price


@dataclass(slots=True)
class Bracket:
    """Exit orders attached to an open position (prices fixed from the actual entry fill)."""

    direction: int  # +1 long, -1 short
    take_profit_price: float | None = None
    stop_price: float | None = None

    @classmethod
    def from_fill(
        cls,
        direction: int,
        fill_price: float,
        *,
        take_profit_pct: float | None,
        stop_loss_pct: float | None,
    ) -> Bracket | None:
        if take_profit_pct is None and stop_loss_pct is None:
            return None
        tp = None if take_profit_pct is None else fill_price * (1.0 + direction * take_profit_pct)
        sl = None if stop_loss_pct is None else fill_price * (1.0 - direction * stop_loss_pct)
        return cls(direction=direction, take_profit_price=tp, stop_price=sl)

    @property
    def exit_side(self) -> Side:
        return "sell" if self.direction > 0 else "buy"

    def stop_hit(self, bar: dict[str, Any]) -> float | None:
        if self.stop_price is None:
            return None
        open_price = float(bar.get("open", bar["close"]))
        if self.direction > 0:
            low = float(bar.get("low", bar["close"]))
            if low <= self.stop_price:
                return min(open_price, self.stop_price)
        else:
            high = float(bar.get("high", bar["close"]))
            if high >= self.stop_price:
                return max(open_price, self.stop_price)
        return None

    def take_profit_hit(self, bar: dict[str, Any]) -> float | None:
        if self.take_profit_price is None:
            return None
        return limit_fill_price(self.exit_side, self.take_profit_price, bar)

    def exit_for_bar(self, bar: dict[str, Any], *, allow_take_profit: bool = True) -> tuple[float, str] | None:
        """``(price, reason)`` for the first exit this bar, stop before take-profit."""
        stop = self.stop_hit(bar)
        if stop is not None:
            return stop, "stop_loss"
        if allow_take_profit:
            tp = self.take_profit_hit(bar)
            if tp is not None:
                return tp, "take_profit"
        return None
