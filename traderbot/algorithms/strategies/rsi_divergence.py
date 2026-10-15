"""RSI divergence swing trades using causally confirmed pivots."""

from __future__ import annotations

from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.patterns.swings import is_confirmed_swing_high, is_confirmed_swing_low
from traderbot.algorithms.streaming import rsi_init, rsi_reset, rsi_update

HISTORY_BARS = 500


class RsiDivergenceAlgorithm(Algorithm):
    """Bullish divergence: a confirmed swing low below the previous one while RSI makes a higher
    low (previous pivot RSI ≤ ``divergence_rsi_level``). Entry waits for confirmation: a close
    above the high of the new pivot bar within ``divergence_confirm_bars``. Stop sits
    ``divergence_stop_buffer_pct`` below the swing low; a trailing stop and bearish divergence
    (higher price high, lower RSI high) close the trade.

    Pivots are only known ``swing_window_bars`` after they print (no lookahead).
    """

    name = "rsi_divergence"

    def __init__(
        self,
        *,
        period = 14,
        swing_window_bars = 3,
        divergence_rsi_level = 40.0,
        divergence_confirm_bars = 5,
        divergence_stop_buffer_pct = 0.005,
        trailing_stop_pct = 0.0,
    ):
        if period < 2:
            raise ValueError("period must be >= 2")
        if swing_window_bars < 1:
            raise ValueError("swing_window_bars must be >= 1")
        if divergence_confirm_bars < 1:
            raise ValueError("divergence_confirm_bars must be >= 1")
        if not 0 <= divergence_stop_buffer_pct < 1 or not 0 <= trailing_stop_pct < 1:
            raise ValueError("stop percentages must be in [0, 1)")
        self.period = period
        self.swing_window_bars = swing_window_bars
        self.divergence_rsi_level = divergence_rsi_level
        self.divergence_confirm_bars = divergence_confirm_bars
        self.divergence_stop_buffer_pct = divergence_stop_buffer_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.reset()

    def reset(self) -> None:
        self._rsi = rsi_init(self.period)
        rsi_reset(self._rsi)
        self._highs: deque[float] = deque(maxlen=HISTORY_BARS)
        self._lows: deque[float] = deque(maxlen=HISTORY_BARS)
        self._rsis: deque[float | None] = deque(maxlen=HISTORY_BARS)
        self._last_low_pivot: tuple[float, float] | None = None
        self._last_high_pivot: tuple[float, float] | None = None
        self._setup: dict[str, float] | None = None
        self._in_position = False
        self._stop_price = 0.0
        self._peak_close = 0.0

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._in_position = False

    def _confirmed_pivot(self, values: deque[float], is_low: bool) -> tuple[float, float, float] | None:
        series = list(values)
        finder = is_confirmed_swing_low if is_low else is_confirmed_swing_high
        pivot_index = finder(series, self.swing_window_bars)
        if pivot_index is None:
            return None
        pivot_rsi = self._rsis[pivot_index]
        if pivot_rsi is None:
            return None
        return series[pivot_index], pivot_rsi, list(self._highs)[pivot_index]

    def on_bar(self, bar: Bar) -> SignalAction:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        self._highs.append(high)
        self._lows.append(low)
        self._rsis.append(rsi_update(self._rsi, close))

        bearish = False
        high_pivot = self._confirmed_pivot(self._highs, is_low=False)
        if high_pivot is not None:
            price, pivot_rsi, _ = high_pivot
            previous = self._last_high_pivot
            bearish = previous is not None and price > previous[0] and pivot_rsi < previous[1]
            self._last_high_pivot = (price, pivot_rsi)

        low_pivot = self._confirmed_pivot(self._lows, is_low=True)
        if low_pivot is not None:
            price, pivot_rsi, pivot_high = low_pivot
            previous = self._last_low_pivot
            if (
                previous is not None
                and price < previous[0]
                and pivot_rsi > previous[1]
                and previous[1] <= self.divergence_rsi_level
            ):
                self._setup = {"swing_low": price, "trigger": pivot_high, "bars_left": self.divergence_confirm_bars}
            self._last_low_pivot = (price, pivot_rsi)

        if self._in_position:
            self._peak_close = max(self._peak_close, close)
            trailing = self.trailing_stop_pct > 0 and close <= self._peak_close * (1 - self.trailing_stop_pct)
            if low <= self._stop_price or trailing or bearish:
                self._in_position = False
                return "sell"
            return "hold"

        if self._setup is not None:
            if close > self._setup["trigger"]:
                self._stop_price = self._setup["swing_low"] * (1 - self.divergence_stop_buffer_pct)
                self._setup = None
                self._in_position = True
                self._peak_close = close
                return "buy"
            self._setup["bars_left"] -= 1
            if self._setup["bars_left"] <= 0 or close < self._setup["swing_low"]:
                self._setup = None
        return "hold"
