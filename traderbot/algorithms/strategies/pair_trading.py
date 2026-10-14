"""Statistical pair trading on a primary series vs a hedge close (Martha Stewart / classic stat arb).

Inspired by pair-trading descriptions in lucylow/Martha_Stewart (educational README) and
spread mean-reversion patterns used in Hummingbot cross-exchange strategies (Apache-2.0).
See docs/third-party-strategies.md for attribution.
"""

from __future__ import annotations

from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.spread import (
    rolling_hedge_ratio,
    spread_zscore_init,
    spread_zscore_reset,
    spread_zscore_update,
)
class PairTradingSpreadAlgorithm(Algorithm):
    """Long primary when its log spread vs hedge is unusually low; exit when normalized spread recovers."""

    name = "pair_trading"

    def __init__(
        self,
        *,
        lookback: int = 60,
        hedge_lookback: int = 60,
        entry_z: float = 2.0,
        exit_z: float = 0.5,
        use_dynamic_hedge_ratio: bool = True,
        fixed_hedge_ratio: float = 1.0,
    ):
        if lookback < 2:
            raise ValueError("lookback must be at least 2")
        if hedge_lookback < 2:
            raise ValueError("hedge_lookback must be at least 2")
        if entry_z <= 0:
            raise ValueError("entry_z must be positive")
        if exit_z < 0:
            raise ValueError("exit_z must be non-negative")
        self.lookback = lookback
        self.hedge_lookback = hedge_lookback
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.use_dynamic_hedge_ratio = use_dynamic_hedge_ratio
        self.fixed_hedge_ratio = fixed_hedge_ratio
        self._zstate = spread_zscore_init(lookback)
        self._primary_window: deque[float] = deque(maxlen=hedge_lookback)
        self._hedge_window: deque[float] = deque(maxlen=hedge_lookback)
        self._in_position = False

    def reset(self) -> None:
        spread_zscore_reset(self._zstate)
        self._primary_window.clear()
        self._hedge_window.clear()
        self._in_position = False

    def sync_open_position(self, in_position: bool) -> None:
        self._in_position = in_position

    def on_bar(self, bar: Bar) -> SignalAction:
        hedge_close = bar.get("hedge_close")
        if hedge_close is None:
            return "hold"
        primary_close = float(bar["close"])
        hedge_value = float(hedge_close)
        self._primary_window.append(primary_close)
        self._hedge_window.append(hedge_value)
        hedge_ratio = self.fixed_hedge_ratio
        if self.use_dynamic_hedge_ratio:
            dynamic = rolling_hedge_ratio(self._primary_window, self._hedge_window)
            if dynamic is not None:
                hedge_ratio = dynamic
        z_score = spread_zscore_update(self._zstate, primary_close, hedge_value, hedge_ratio)
        if z_score is None:
            return "hold"
        if not self._in_position and z_score <= -self.entry_z:
            self._in_position = True
            return "buy"
        if self._in_position and z_score >= -self.exit_z:
            self._in_position = False
            return "sell"
        return "hold"
