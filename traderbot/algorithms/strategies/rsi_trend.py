"""RSI momentum: ride strength above a midline instead of fading it."""

from __future__ import annotations

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.streaming import ema_init, ema_reset, ema_update, rsi_init, rsi_reset, rsi_update


class RsiTrendAlgorithm(Algorithm):
    """Buy when RSI crosses up through ``rsi_trend_entry`` with close above the EMA trend filter;
    exit when RSI crosses down through ``rsi_trend_exit`` or close loses the filter."""

    name = "rsi_trend"

    def __init__(
        self,
        *,
        period = 14,
        rsi_trend_entry = 55.0,
        rsi_trend_exit = 45.0,
        trend_filter_period = 50,
    ):
        if period < 2:
            raise ValueError("period must be >= 2")
        if not 0 < rsi_trend_exit < rsi_trend_entry < 100:
            raise ValueError("need 0 < rsi_trend_exit < rsi_trend_entry < 100")
        if trend_filter_period < 1:
            raise ValueError("trend_filter_period must be >= 1")
        self.period = period
        self.rsi_trend_entry = rsi_trend_entry
        self.rsi_trend_exit = rsi_trend_exit
        self.trend_filter_period = trend_filter_period
        self._rsi = rsi_init(period)
        self._ema = ema_init(trend_filter_period)
        self._bar_count = 0
        self._prev_rsi: float | None = None
        self._in_position = False

    def reset(self) -> None:
        rsi_reset(self._rsi)
        ema_reset(self._ema)
        self._bar_count = 0
        self._prev_rsi = None
        self._in_position = False

    def sync_open_position(self, in_position: bool) -> None:
        self._in_position = in_position

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._bar_count += 1
        current_rsi = rsi_update(self._rsi, close)
        trend = ema_update(self._ema, close)
        prev_rsi = self._prev_rsi
        self._prev_rsi = current_rsi
        if current_rsi is None or prev_rsi is None or self._bar_count < self.trend_filter_period:
            return "hold"
        if self._in_position:
            if (prev_rsi >= self.rsi_trend_exit > current_rsi) or close < trend:
                self._in_position = False
                return "sell"
            return "hold"
        if prev_rsi < self.rsi_trend_entry <= current_rsi and close > trend:
            self._in_position = True
            return "buy"
        return "hold"
