"""Event/news momentum via a pluggable event source (default: price/volume shock proxy)."""

from __future__ import annotations

import math
from collections import deque
from typing import Protocol

from traderbot.algorithms.base import Algorithm, Bar, SignalAction


class EventSignalSource(Protocol):
    """Scores the latest closed bar: > 0 bullish event, < 0 bearish, 0 none.

    Implementations must only use information available at the bar close. Plug a real
    news/on-chain feed in here; the default is :class:`PriceVolumeShockSource`.
    """

    def reset(self) -> None: ...

    def score_bar(self, bar: Bar) -> float: ...


class PriceVolumeShockSource:
    """PROXY, not news: a bar whose return exceeds ``shock_return_std`` rolling standard deviations
    on volume ≥ ``shock_volume_multiplier`` × average is treated as an event."""

    def __init__(self, *, lookback_bars = 20, shock_return_std = 2.5, shock_volume_multiplier = 2.0):
        self.lookback_bars = lookback_bars
        self.shock_return_std = shock_return_std
        self.shock_volume_multiplier = shock_volume_multiplier
        self.reset()

    def reset(self) -> None:
        self._returns: deque[float] = deque(maxlen=self.lookback_bars)
        self._volumes: deque[float] = deque(maxlen=self.lookback_bars)
        self._prev_close: float | None = None

    def score_bar(self, bar: Bar) -> float:
        close = float(bar["close"])
        volume = float(bar.get("volume") or 0.0)
        prev_close = self._prev_close
        self._prev_close = close
        if prev_close is None or prev_close <= 0:
            self._volumes.append(volume)
            return 0.0
        bar_return = close / prev_close - 1.0
        returns, volumes = list(self._returns), list(self._volumes)
        self._returns.append(bar_return)
        self._volumes.append(volume)
        if len(returns) < self.lookback_bars:
            return 0.0
        mean = sum(returns) / len(returns)
        deviation = math.sqrt(sum((value - mean) ** 2 for value in returns) / (len(returns) - 1))
        average_volume = sum(volumes) / len(volumes)
        if deviation <= 0:
            return 0.0
        z_score = (bar_return - mean) / deviation
        volume_ok = average_volume <= 0 or volume >= self.shock_volume_multiplier * average_volume
        if abs(z_score) < self.shock_return_std or not volume_ok:
            return 0.0
        return z_score


class MomentumShockAlgorithm(Algorithm):
    """Buy after a bullish event score; exit after ``shock_hold_bars`` bars, on a bearish event,
    or on the trailing stop. Default source is a price/volume shock proxy — no news data."""

    name = "momentum_shock"

    def __init__(
        self,
        *,
        lookback_bars = 20,
        shock_return_std = 2.5,
        shock_volume_multiplier = 2.0,
        shock_hold_bars = 12,
        trailing_stop_pct = 0.0,
        event_source: EventSignalSource | None = None,
    ):
        if lookback_bars < 3:
            raise ValueError("lookback_bars must be >= 3")
        if shock_return_std <= 0 or shock_volume_multiplier < 0:
            raise ValueError("shock thresholds must be positive")
        if shock_hold_bars < 1:
            raise ValueError("shock_hold_bars must be >= 1")
        if not 0 <= trailing_stop_pct < 1:
            raise ValueError("trailing_stop_pct must be in [0, 1)")
        self.shock_hold_bars = shock_hold_bars
        self.trailing_stop_pct = trailing_stop_pct
        self.event_source: EventSignalSource = event_source or PriceVolumeShockSource(
            lookback_bars=lookback_bars,
            shock_return_std=shock_return_std,
            shock_volume_multiplier=shock_volume_multiplier,
        )
        self.reset()

    def reset(self) -> None:
        self.event_source.reset()
        self._bars_held = 0
        self._in_position = False
        self._peak_close = 0.0

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._in_position = False

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        score = self.event_source.score_bar(bar)
        if self._in_position:
            self._bars_held += 1
            self._peak_close = max(self._peak_close, close)
            trailing = self.trailing_stop_pct > 0 and close <= self._peak_close * (1 - self.trailing_stop_pct)
            if self._bars_held >= self.shock_hold_bars or score < 0 or trailing:
                self._in_position = False
                return "sell"
            return "hold"
        if score > 0:
            self._in_position = True
            self._bars_held = 0
            self._peak_close = close
            return "buy"
        return "hold"
