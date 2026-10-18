"""
Long-only spot grid inspired by Hummingbot GridStrike / grid executor (Apache-2.0).

Buys when price dips to the next lower grid level inside [start_price, end_price];
sells when price reaches take-profit above the entry. Suited to ranging Nobitex spot
pairs when liquidity allows limit-style fills near the close.
"""

from __future__ import annotations

from typing import Any

from traderbot.algorithms.base import Algorithm, Bar, SignalAction


def grid_price_bounds_from_bars(bars: list[dict[str, Any]]) -> tuple[float, float]:
    """Train-window style bounds for backtests when grid limits are not set explicitly."""
    if not bars:
        raise ValueError("grid_price_bounds_from_bars requires at least one bar")
    closes = [float(bar["close"]) for bar in bars]
    low = min(closes)
    high = max(closes)
    padding = (high - low) * 0.05 or high * 0.02
    return low - padding, high + padding


def _linear_grid_levels(start_price: float, end_price: float, grid_count: int) -> list[float]:
    if grid_count < 1:
        raise ValueError("grid_count must be >= 1")
    if end_price <= start_price:
        raise ValueError("end_price must be greater than start_price")
    if grid_count == 1:
        return [(start_price + end_price) / 2.0]
    step = (end_price - start_price) / (grid_count - 1)
    return [start_price + step * index for index in range(grid_count)]


class SpotGridAlgorithm(Algorithm):
    name = "spot_grid"

    def __init__(
        self,
        *,
        start_price: float,
        end_price: float,
        grid_count: int = 5,
        take_profit_pct: float = 0.01,
    ):
        if start_price <= 0 or end_price <= 0:
            raise ValueError("grid prices must be positive")
        if take_profit_pct <= 0:
            raise ValueError("take_profit_pct must be positive")
        self.start_price = start_price
        self.end_price = end_price
        self.grid_count = grid_count
        self.take_profit_pct = take_profit_pct
        self._levels = _linear_grid_levels(start_price, end_price, grid_count)
        self._entry_price: float | None = None
        self._next_buy_level_index: int = grid_count - 1
        self._last_close: float | None = None

    def reset(self) -> None:
        self._entry_price = None
        self._next_buy_level_index = self.grid_count - 1
        self._last_close = None

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._entry_price = None

    def _sync_buy_level_index(self, close: float) -> None:
        level_index = self.grid_count - 1
        while level_index >= 0 and self._levels[level_index] > close:
            level_index -= 1
        self._next_buy_level_index = level_index

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        low = float(bar.get("low", close))
        high = float(bar.get("high", close))
        if self._last_close is None:
            self._sync_buy_level_index(close)
        self._last_close = close

        if self._entry_price is not None:
            target = self._entry_price * (1.0 + self.take_profit_pct)
            if high >= target:
                self._entry_price = None
                self._sync_buy_level_index(close)
                return "sell"
            return "hold"

        if close < self.start_price or close > self.end_price:
            return "hold"

        while self._next_buy_level_index >= 0:
            level_price = self._levels[self._next_buy_level_index]
            if low <= level_price:
                self._entry_price = level_price
                self._next_buy_level_index -= 1
                return "buy"
            break

        return "hold"
