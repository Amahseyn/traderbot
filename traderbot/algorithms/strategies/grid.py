"""Range grid: hold more inventory near the bottom of a range, less near the top."""

from __future__ import annotations

import math
from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, SignalAction


class GridAlgorithm(Algorithm):
    """After ``lookback_bars`` bars, the range is anchored at the mean close ± ``grid_range_pct``.
    The range is split into ``grid_levels`` bands; target exposure rises one step per band
    the close falls (full at the lower bound, flat at the upper). Crossing into a new band
    rebalances. A close beyond either bound by ``grid_breakout_pct`` sells everything and shuts
    the grid down; with ``grid_reanchor_bars`` > 0 it re-anchors after that many bars.
    """

    name = "grid"
    uses_position_sizing = True

    def __init__(
        self,
        *,
        lookback_bars = 20,
        grid_range_pct = 0.05,
        grid_levels = 5,
        grid_breakout_pct = 0.01,
        grid_reanchor_bars = 0,
    ):
        if lookback_bars < 1:
            raise ValueError("lookback_bars must be >= 1")
        if not 0 < grid_range_pct < 1:
            raise ValueError("grid_range_pct must be in (0, 1)")
        if grid_levels < 2:
            raise ValueError("grid_levels must be >= 2")
        if grid_breakout_pct < 0:
            raise ValueError("grid_breakout_pct must be >= 0")
        if grid_reanchor_bars < 0:
            raise ValueError("grid_reanchor_bars must be >= 0")
        self.lookback_bars = lookback_bars
        self.grid_range_pct = grid_range_pct
        self.grid_levels = grid_levels
        self.grid_breakout_pct = grid_breakout_pct
        self.grid_reanchor_bars = grid_reanchor_bars
        self.reset()

    def reset(self) -> None:
        self._closes: deque[float] = deque(maxlen=self.lookback_bars)
        self._lower = 0.0
        self._upper = 0.0
        self._band: int | None = None
        self._shutdown_bars: int | None = None
        self._size: OrderSize | None = None

    def order_size(self) -> OrderSize | None:
        return self._size

    @property
    def is_shut_down(self) -> bool:
        return self._shutdown_bars is not None

    def _band_for(self, close: float) -> int:
        step = (self._upper - self._lower) / self.grid_levels
        band = math.floor((close - self._lower) / step)
        return min(max(band, 0), self.grid_levels - 1)

    def _exposure_for(self, band: int) -> float:
        return 1.0 - band / (self.grid_levels - 1)

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._closes.append(close)
        self._size = None

        if self._shutdown_bars is not None:
            if self.grid_reanchor_bars <= 0:
                return "hold"
            self._shutdown_bars += 1
            if self._shutdown_bars < self.grid_reanchor_bars:
                return "hold"
            self._shutdown_bars = None
            self._band = None

        if self._band is None:
            if len(self._closes) < self.lookback_bars:
                return "hold"
            anchor = sum(self._closes) / len(self._closes)
            self._lower = anchor * (1 - self.grid_range_pct)
            self._upper = anchor * (1 + self.grid_range_pct)
            self._band = self._band_for(close)
            self._size = OrderSize(target_exposure=self._exposure_for(self._band))
            return "buy" if self._size.target_exposure and self._size.target_exposure > 0 else "hold"

        broke_out = close > self._upper * (1 + self.grid_breakout_pct) or close < self._lower * (
            1 - self.grid_breakout_pct
        )
        if broke_out:
            self._shutdown_bars = 0
            self._size = OrderSize(target_exposure=0.0)
            return "sell"

        band = self._band_for(close)
        if band == self._band:
            return "hold"
        action: SignalAction = "buy" if band < self._band else "sell"
        self._band = band
        self._size = OrderSize(target_exposure=self._exposure_for(band))
        return action
