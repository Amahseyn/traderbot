from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.streaming import atr_init, atr_reset, atr_update


class BreakoutAtrAlgorithm(Algorithm):
    """Enter long on close above recent high + ATR buffer; exit on breakdown or ATR stop."""

    name = "breakout_atr"

    def __init__(
        self,
        *,
        lookback_bars = 20,
        atr_period = 14,
        atr_multiplier = 1.5,
        stop_atr_multiplier = 1.0,
    ):
        if lookback_bars < 2:
            raise ValueError("lookback_bars must be >= 2")
        if atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if atr_multiplier <= 0:
            raise ValueError("atr_multiplier must be positive")
        if stop_atr_multiplier <= 0:
            raise ValueError("stop_atr_multiplier must be positive")
        self.lookback_bars = lookback_bars
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.stop_atr_multiplier = stop_atr_multiplier
        self._highs: deque[float] = deque(maxlen=lookback_bars + 1)
        self._lows: deque[float] = deque(maxlen=lookback_bars + 1)
        self._atr = atr_init(atr_period)
        self._in_long = False
        self._stop_price: float | None = None

    def reset(self) -> None:
        self._highs.clear()
        self._lows.clear()
        atr_reset(self._atr)
        self._in_long = False
        self._stop_price = None

    def on_bar(self, bar: Bar) -> SignalAction:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        self._highs.append(high)
        self._lows.append(low)
        atr_now = atr_update(self._atr, high=high, low=low, close=close)
        if len(self._highs) < self.lookback_bars + 1 or atr_now is None:
            return "hold"

        highs = list(self._highs)
        lows = list(self._lows)
        prior_highs = highs[:-1]
        prior_lows = lows[:-1]
        range_high = max(prior_highs)
        range_low = min(prior_lows)
        upper_break = range_high + self.atr_multiplier * atr_now
        lower_break = range_low - self.atr_multiplier * atr_now

        if self._in_long:
            if self._stop_price is not None and low <= self._stop_price:
                self._in_long = False
                self._stop_price = None
                return "sell"
            if close < lower_break:
                self._in_long = False
                self._stop_price = None
                return "sell"
            return "hold"

        if close > upper_break:
            self._in_long = True
            self._stop_price = close - self.stop_atr_multiplier * atr_now
            return "buy"
        return "hold"
