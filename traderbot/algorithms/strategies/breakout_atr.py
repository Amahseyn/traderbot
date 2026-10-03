from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.utils.indicators import atr


class BreakoutAtrAlgorithm(Algorithm):
    """Enter long on close above recent high + ATR buffer; flat on breakdown below range."""

    name = "breakout_atr"

    def __init__(
        self,
        *,
        lookback_bars = 20,
        atr_period = 14,
        atr_multiplier = 1.5,
    ):
        if lookback_bars < 2:
            raise ValueError("lookback_bars must be >= 2")
        if atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if atr_multiplier <= 0:
            raise ValueError("atr_multiplier must be positive")
        self.lookback_bars = lookback_bars
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        history = max(lookback_bars + 1, atr_period + 2)
        self._highs: deque[float] = deque(maxlen=history)
        self._lows: deque[float] = deque(maxlen=history)
        self._closes: deque[float] = deque(maxlen=history)

    def reset(self) -> None:
        self._highs.clear()
        self._lows.clear()
        self._closes.clear()

    def on_bar(self, bar: Bar) -> SignalAction:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)
        if len(self._closes) < self.lookback_bars + 1:
            return "hold"

        highs = list(self._highs)
        lows = list(self._lows)
        closes = list(self._closes)
        atr_values = atr(highs, lows, closes, period=self.atr_period)
        atr_now = atr_values[-1]
        if atr_now is None:
            return "hold"

        prior_highs = highs[-(self.lookback_bars + 1) : -1]
        prior_lows = lows[-(self.lookback_bars + 1) : -1]
        range_high = max(prior_highs)
        range_low = min(prior_lows)
        upper_break = range_high + self.atr_multiplier * atr_now
        lower_break = range_low - self.atr_multiplier * atr_now

        if close > upper_break:
            return "buy"
        if close < lower_break:
            return "sell"
        return "hold"
