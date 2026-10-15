"""Consolidation breakout with volume confirmation and measured-move target."""

from __future__ import annotations

from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, SignalAction


class RangeBreakoutAlgorithm(Algorithm):
    """A range is a consolidation when (high − low) / mean close over ``lookback_bars`` prior bars
    is at most ``range_max_width_pct``. Buy when the close breaks above the range high on volume
    ≥ ``breakout_volume_multiplier`` × the range's average volume. Stop: range high minus
    ``breakout_stop_fraction`` of the range height (just below the breakout). Target: range
    high + range height × ``measured_move_multiplier``.

    The range uses bars strictly before the signal bar (no lookahead).
    """

    name = "range_breakout"

    def __init__(
        self,
        *,
        lookback_bars = 20,
        range_max_width_pct = 0.06,
        breakout_volume_multiplier = 1.5,
        breakout_stop_fraction = 0.5,
        measured_move_multiplier = 1.0,
    ):
        if lookback_bars < 2:
            raise ValueError("lookback_bars must be >= 2")
        if range_max_width_pct <= 0:
            raise ValueError("range_max_width_pct must be positive")
        if breakout_volume_multiplier < 0:
            raise ValueError("breakout_volume_multiplier must be >= 0")
        if not 0 < breakout_stop_fraction <= 1:
            raise ValueError("breakout_stop_fraction must be in (0, 1]")
        if measured_move_multiplier <= 0:
            raise ValueError("measured_move_multiplier must be positive")
        self.lookback_bars = lookback_bars
        self.range_max_width_pct = range_max_width_pct
        self.breakout_volume_multiplier = breakout_volume_multiplier
        self.breakout_stop_fraction = breakout_stop_fraction
        self.measured_move_multiplier = measured_move_multiplier
        self.reset()

    def reset(self) -> None:
        self._bars: deque[tuple[float, float, float, float]] = deque(maxlen=self.lookback_bars)
        self._in_position = False
        self._stop_price = 0.0
        self._target_price = 0.0

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._in_position = False

    def on_bar(self, bar: Bar) -> SignalAction:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        volume = float(bar.get("volume") or 0.0)
        prior = list(self._bars)
        self._bars.append((high, low, close, volume))

        if self._in_position:
            if low <= self._stop_price or high >= self._target_price:
                self._in_position = False
                return "sell"
            return "hold"
        if len(prior) < self.lookback_bars:
            return "hold"

        range_high = max(item[0] for item in prior)
        range_low = min(item[1] for item in prior)
        mean_close = sum(item[2] for item in prior) / len(prior)
        average_volume = sum(item[3] for item in prior) / len(prior)
        height = range_high - range_low
        if mean_close <= 0 or height <= 0 or height / mean_close > self.range_max_width_pct:
            return "hold"
        volume_confirmed = average_volume <= 0 or volume >= self.breakout_volume_multiplier * average_volume
        if close > range_high and volume_confirmed:
            self._in_position = True
            self._stop_price = range_high - self.breakout_stop_fraction * height
            self._target_price = range_high + self.measured_move_multiplier * height
            return "buy"
        return "hold"
