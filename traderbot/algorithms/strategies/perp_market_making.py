"""
Simplified maker-style quotes on OHLC (Hyperliquid fee tier). Inspired by Hummingbot PMM; not a full order book sim.
"""

from __future__ import annotations

from traderbot.algorithms.base import Algorithm, Bar, SignalAction


class PerpMarketMakingAlgorithm(Algorithm):
    name = "perp_market_making"

    def __init__(self, *, half_spread_pct: float = 0.0005, inventory_skew: float = 0.0):
        if half_spread_pct <= 0:
            raise ValueError("half_spread_pct must be positive")
        self.half_spread_pct = half_spread_pct
        self.inventory_skew = inventory_skew
        self._in_position = False

    def reset(self) -> None:
        self._in_position = False

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        low = float(bar.get("low", close))
        high = float(bar.get("high", close))
        bid = close * (1.0 - self.half_spread_pct - self.inventory_skew)
        ask = close * (1.0 + self.half_spread_pct - self.inventory_skew)

        if not self._in_position and low <= bid:
            self._in_position = True
            return "buy"
        if self._in_position and high >= ask:
            self._in_position = False
            return "sell"
        return "hold"
