"""FinRL-Trading intraday preset: EMA 12/48 (Hyperliquid 1m/5m research default)."""

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, SignalAction
from traderbot.algorithms.position_sizing import ALL_IN_EXPOSURE, entry_order_size, validate_target_exposure
from traderbot.algorithms.price_context import (
    apply_intrahour_context,
    recent_cumulative_return,
    recent_return_gate,
    trend_edge_window_bars,
    trend_signal_clears_cost,
)
from traderbot.algorithms.signals import signal_from_cross
from traderbot.algorithms.streaming import ema_init, ema_reset, ema_update
from traderbot.algorithms.validators import validate_cost_edge, validate_fast_slow, validate_price_context


class FinrlEmaIntradayAlgorithm(Algorithm):
    """
    FinRL-aligned intraday EMA preset.

    ``signal_style='level_lag'`` (default): long when lagged fast EMA > slow EMA, matching
    FinRL ``ema_cross_signals`` (``raw.shift(1)``). ``signal_style='cross'``: event-based
    crossover like ``ema_cross``.
    """

    name = "finrl_ema_intraday"

    def __init__(
        self,
        *,
        fast: int = 12,
        slow: int = 48,
        price_confirm: bool = False,
        signal_style: str = "level_lag",
        context_bars: int = 0,
        buy_min_recent_return: float = 0.0,
        sell_max_recent_return: float = 0.0,
        buy_min_fine_last_5m: float | None = None,
        sell_max_fine_last_5m: float | None = None,
        min_edge_over_cost: float | None = None,
        roundtrip_cost_pct: float | None = None,
        target_exposure: float = 1.0,
    ):
        validate_fast_slow(fast, slow)
        validate_price_context(context_bars, buy_min_recent_return, sell_max_recent_return)
        validate_cost_edge(min_edge_over_cost, roundtrip_cost_pct)
        self.target_exposure = validate_target_exposure(target_exposure)
        if self.target_exposure < ALL_IN_EXPOSURE:
            self.uses_position_sizing = True
        if signal_style not in ("level_lag", "cross"):
            raise ValueError("signal_style must be 'level_lag' or 'cross'")
        self.fast = fast
        self.slow = slow
        self.price_confirm = price_confirm
        self.signal_style = signal_style
        self.context_bars = context_bars
        self.buy_min_recent_return = buy_min_recent_return
        self.sell_max_recent_return = sell_max_recent_return
        self.buy_min_fine_last_5m = buy_min_fine_last_5m
        self.sell_max_fine_last_5m = sell_max_fine_last_5m
        self.min_edge_over_cost = 0.0 if min_edge_over_cost is None else float(min_edge_over_cost)
        self.roundtrip_cost_pct = roundtrip_cost_pct
        self._fast = ema_init(fast)
        self._slow = ema_init(slow)
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None
        self._prev_want_long: bool | None = None
        self._held_long = False
        self._closes: list[float] = []
        self._size: OrderSize | None = None

    def reset(self) -> None:
        ema_reset(self._fast)
        ema_reset(self._slow)
        self._prev_fast = None
        self._prev_slow = None
        self._prev_want_long = None
        self._held_long = False
        self._closes.clear()
        self._size = None

    def order_size(self) -> OrderSize | None:
        return self._size

    def sync_open_position(self, in_position: bool) -> None:
        self._held_long = in_position

    def _gate_signal(self, action: SignalAction, bar: Bar) -> SignalAction:
        if action == "hold":
            return "hold"
        window_bars = trend_edge_window_bars(self.context_bars, self.slow)
        if not trend_signal_clears_cost(
            action,
            recent_cumulative_return(self._closes, window_bars),
            roundtrip_cost_pct=self.roundtrip_cost_pct,
            min_edge_over_cost=self.min_edge_over_cost,
        ):
            return "hold"
        action = recent_return_gate(
            action,
            self._closes,
            context_bars=self.context_bars,
            buy_min_recent_return=self.buy_min_recent_return,
            sell_max_recent_return=self.sell_max_recent_return,
        )
        return apply_intrahour_context(
            action,
            bar,
            buy_min_fine_last_5m=self.buy_min_fine_last_5m,
            sell_max_fine_last_5m=self.sell_max_fine_last_5m,
        )

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._closes.append(close)
        if self.signal_style == "cross":
            action = self._on_bar_cross(bar)
        else:
            action = self._on_bar_level_lag(bar)
        action = self._gate_signal(action, bar)
        if action != "hold":
            self._size = entry_order_size(self.target_exposure, action)
        return action

    def _on_bar_cross(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        fast_v = ema_update(self._fast, close)
        slow_v = ema_update(self._slow, close)
        action = signal_from_cross(self._prev_fast, self._prev_slow, fast_v, slow_v)
        self._prev_fast = fast_v
        self._prev_slow = slow_v
        if not self.price_confirm or action == "hold":
            return action
        if fast_v is None:
            return "hold"
        if action == "buy" and close < fast_v:
            return "hold"
        if action == "sell" and close > fast_v:
            return "hold"
        return action

    def _on_bar_level_lag(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        fast_v = ema_update(self._fast, close)
        slow_v = ema_update(self._slow, close)
        want_long = (
            fast_v is not None and slow_v is not None and fast_v > slow_v
        )
        lagged_target = self._prev_want_long
        self._prev_want_long = want_long
        if lagged_target is None:
            return "hold"
        if lagged_target and not self._held_long:
            self._held_long = True
            return "buy"
        if not lagged_target and self._held_long:
            self._held_long = False
            return "sell"
        return "hold"
