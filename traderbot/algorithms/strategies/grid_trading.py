"""Long-only grid dip buyer adapted from Hummingbot ``grid_strike`` (Apache-2.0).

Places buy levels between anchor*(1+low_pct) and anchor*(1+high_pct); takes profit after
``take_profit_pct`` from entry. See docs/third-party-strategies.md.
"""

from __future__ import annotations

from traderbot.algorithms.base import Algorithm, Bar, SignalAction


class GridTradingAlgorithm(Algorithm):
    name = "grid_trading"

    def __init__(
        self,
        *,
        grid_low_pct: float = -0.08,
        grid_high_pct: float = 0.04,
        grid_levels: int = 5,
        take_profit_pct: float = 0.01,
    ):
        if grid_low_pct >= grid_high_pct:
            raise ValueError("grid_low_pct must be below grid_high_pct")
        if grid_levels < 2:
            raise ValueError("grid_levels must be at least 2")
        if take_profit_pct <= 0:
            raise ValueError("take_profit_pct must be positive")
        self.grid_low_pct = grid_low_pct
        self.grid_high_pct = grid_high_pct
        self.grid_levels = grid_levels
        self.take_profit_pct = take_profit_pct
        self._grid_prices: list[float] = []
        self._prev_close: float | None = None
        self._entry_price: float | None = None
        self._triggered_levels: set[float] = set()
        self._anchor_set = False

    def _build_grid(self, anchor: float) -> None:
        low = anchor * (1.0 + self.grid_low_pct)
        high = anchor * (1.0 + self.grid_high_pct)
        step = (high - low) / (self.grid_levels - 1)
        self._grid_prices = [low + step * level_index for level_index in range(self.grid_levels)]

    def reset(self) -> None:
        self._grid_prices = []
        self._prev_close = None
        self._entry_price = None
        self._triggered_levels.clear()
        self._anchor_set = False

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._entry_price = None

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        if not self._anchor_set:
            self._build_grid(close)
            self._anchor_set = True
        if self._prev_close is None:
            self._prev_close = close
            return "hold"
        if self._entry_price is not None:
            target = self._entry_price * (1.0 + self.take_profit_pct)
            if close >= target:
                self._entry_price = None
                self._prev_close = close
                return "sell"
            self._prev_close = close
            return "hold"
        for level in self._grid_prices:
            if level in self._triggered_levels:
                continue
            if self._prev_close > level >= close:
                self._triggered_levels.add(level)
                self._entry_price = close
                self._prev_close = close
                return "buy"
        self._prev_close = close
        return "hold"
