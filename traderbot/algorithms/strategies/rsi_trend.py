"""RSI momentum: ride strength above a midline instead of fading it."""

from __future__ import annotations

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, SignalAction
from traderbot.algorithms.position_sizing import EntryTranches
from traderbot.algorithms.price_context import (
    recent_cumulative_return,
    trend_signal_clears_cost,
)
from traderbot.algorithms.streaming import ema_init, ema_reset, ema_update, rsi_init, rsi_reset, rsi_update
from traderbot.algorithms.validators import validate_cost_edge


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
        stop_loss_pct: float | None = None,
        trailing_stop_pct: float | None = None,
        min_edge_over_cost: float | None = None,
        roundtrip_cost_pct: float | None = None,
        target_exposure: float = 1.0,
        max_tranches: int = 1,
        tranche_gap_bars: int = 0,
    ):
        if period < 2:
            raise ValueError("period must be >= 2")
        if not 0 < rsi_trend_exit < rsi_trend_entry < 100:
            raise ValueError("need 0 < rsi_trend_exit < rsi_trend_entry < 100")
        if trend_filter_period < 1:
            raise ValueError("trend_filter_period must be >= 1")
        if stop_loss_pct is not None and stop_loss_pct <= 0:
            raise ValueError("stop_loss_pct must be positive")
        if trailing_stop_pct is not None and trailing_stop_pct <= 0:
            raise ValueError("trailing_stop_pct must be positive")
        validate_cost_edge(min_edge_over_cost, roundtrip_cost_pct)
        self._entries = EntryTranches(
            target_exposure=target_exposure,
            max_tranches=max_tranches,
            tranche_gap_bars=tranche_gap_bars,
        )
        self.target_exposure = self._entries.target_exposure
        if self._entries.partial:
            self.uses_position_sizing = True
        self.period = period
        self.rsi_trend_entry = rsi_trend_entry
        self.rsi_trend_exit = rsi_trend_exit
        self.trend_filter_period = trend_filter_period
        self.stop_loss_pct = float(stop_loss_pct) if stop_loss_pct is not None else None
        self.trailing_stop_pct = float(trailing_stop_pct) if trailing_stop_pct is not None else None
        self.min_edge_over_cost = 0.0 if min_edge_over_cost is None else float(min_edge_over_cost)
        self.roundtrip_cost_pct = roundtrip_cost_pct
        self._rsi = rsi_init(period)
        self._ema = ema_init(trend_filter_period)
        self._bar_count = 0
        self._prev_rsi: float | None = None
        self._in_position = False
        self._entry_price = 0.0
        self._highest_price = 0.0
        self._closes: list[float] = []
        self._size: OrderSize | None = None

    def reset(self) -> None:
        rsi_reset(self._rsi)
        ema_reset(self._ema)
        self._bar_count = 0
        self._prev_rsi = None
        self._in_position = False
        self._entry_price = 0.0
        self._highest_price = 0.0
        self._closes.clear()
        self._size = None
        self._entries.reset()

    def order_size(self) -> OrderSize | None:
        return self._size

    def sync_open_position(self, in_position: bool) -> None:
        self._in_position = in_position
        if not in_position:
            self._entries.reset()

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._entries.tick()
        self._closes.append(close)
        self._bar_count += 1
        current_rsi = rsi_update(self._rsi, close)
        trend = ema_update(self._ema, close)
        prev_rsi = self._prev_rsi
        self._prev_rsi = current_rsi
        if current_rsi is None or prev_rsi is None or self._bar_count < self.trend_filter_period:
            return "hold"
        crossed_up = prev_rsi < self.rsi_trend_entry <= current_rsi and close > trend
        if self._in_position:
            self._highest_price = max(self._highest_price, close)
            stopped_out = (
                (self.stop_loss_pct is not None and close <= self._entry_price * (1.0 - self.stop_loss_pct))
                or (self.trailing_stop_pct is not None and close <= self._highest_price * (1.0 - self.trailing_stop_pct))
            )
            if (prev_rsi >= self.rsi_trend_exit > current_rsi) or close < trend or stopped_out:
                self._in_position = False
                self._size = self._entries.note_exit()
                return "sell"
            if crossed_up and self._entries.allows_entry():
                self._size = self._entries.note_entry()
                return "buy"
            return "hold"
        if crossed_up:
            move_pct = recent_cumulative_return(self._closes, self.period)
            if not trend_signal_clears_cost(
                "buy",
                move_pct,
                roundtrip_cost_pct=self.roundtrip_cost_pct,
                min_edge_over_cost=self.min_edge_over_cost,
            ):
                return "hold"
            self._in_position = True
            self._entry_price = close
            self._highest_price = close
            self._size = self._entries.note_entry()
            return "buy"
        return "hold"
