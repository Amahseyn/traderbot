from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, OrderSpec, SignalAction
from traderbot.algorithms.entry_orders import MakerEntry
from traderbot.algorithms.price_context import (
    apply_intrahour_context,
    recent_cumulative_return,
    recent_return_gate,
    trend_edge_window_bars,
    trend_signal_clears_cost,
)
from traderbot.algorithms.signals import signal_from_cross
from traderbot.algorithms.streaming import rolling_mean_init, rolling_mean_reset, rolling_mean_update
from traderbot.algorithms.validators import validate_cost_edge, validate_fast_slow, validate_price_context


class SmaCrossAlgorithm(Algorithm):
    """Go long when fast SMA is above slow SMA; flat when below.

    Three optional gates keep 1-minute crossovers from firing on noise that cannot pay for a
    roundtrip: ``price_confirm`` (close on the trend side of the fast average), the recent-path
    filter (``context_bars`` + ``buy_min_recent_return`` / ``sell_max_recent_return``) and
    ``min_edge_over_cost`` (the move behind the cross must clear the venue friction).
    """

    name = "sma_cross"

    def __init__(
        self,
        *,
        fast = 5,
        slow = 20,
        price_confirm = False,
        context_bars = 0,
        buy_min_recent_return = 0.0,
        sell_max_recent_return = 0.0,
        buy_min_fine_last_5m: float | None = None,
        sell_max_fine_last_5m: float | None = None,
        min_edge_over_cost: float | None = None,
        roundtrip_cost_pct: float | None = None,
        entry_order_mode: str = "market",
        entry_offset_pct: float = 0.0002,
        entry_ttl_bars: int = 2,
    ):
        validate_fast_slow(fast, slow)
        validate_price_context(context_bars, buy_min_recent_return, sell_max_recent_return)
        validate_cost_edge(min_edge_over_cost, roundtrip_cost_pct)
        self.fast = fast
        self.slow = slow
        self.price_confirm = price_confirm
        self.context_bars = context_bars
        self.buy_min_recent_return = buy_min_recent_return
        self.sell_max_recent_return = sell_max_recent_return
        self.buy_min_fine_last_5m = buy_min_fine_last_5m
        self.sell_max_fine_last_5m = sell_max_fine_last_5m
        # ``None`` keeps the gate off for direct construction; the backtest namespace
        # resolves it from the bar size (see strategy_defaults).
        self.min_edge_over_cost = 0.0 if min_edge_over_cost is None else float(min_edge_over_cost)
        self.roundtrip_cost_pct = roundtrip_cost_pct
        self._entry = MakerEntry(
            entry_order_mode=entry_order_mode,
            entry_offset_pct=entry_offset_pct,
            entry_ttl_bars=entry_ttl_bars,
        )
        self._fast = rolling_mean_init(fast)
        self._slow = rolling_mean_init(slow)
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None
        self._closes: deque[float] = deque(maxlen=max(fast, slow, context_bars, 1) + 1)
        self._spec: OrderSpec | None = None

    @property
    def entry_order_mode(self) -> str:
        return self._entry.entry_order_mode

    @property
    def uses_order_engine(self) -> bool:
        return self._entry.is_maker

    def order_spec(self) -> OrderSpec | None:
        return self._spec

    def reset(self) -> None:
        rolling_mean_reset(self._fast)
        rolling_mean_reset(self._slow)
        self._prev_fast = None
        self._prev_slow = None
        self._closes.clear()
        self._spec = None

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._closes.append(close)
        self._spec = None
        fast_v = rolling_mean_update(self._fast, close)
        slow_v = rolling_mean_update(self._slow, close)
        action = signal_from_cross(self._prev_fast, self._prev_slow, fast_v, slow_v)
        self._prev_fast = fast_v
        self._prev_slow = slow_v
        if action == "hold":
            return action
        if self.price_confirm:
            if fast_v is None:
                return "hold"
            if action == "buy" and close < fast_v:
                return "hold"
            if action == "sell" and close > fast_v:
                return "hold"
        closes = list(self._closes)
        window_bars = trend_edge_window_bars(self.context_bars, self.slow)
        if not trend_signal_clears_cost(
            action,
            recent_cumulative_return(closes, window_bars),
            roundtrip_cost_pct=self.roundtrip_cost_pct,
            min_edge_over_cost=self.min_edge_over_cost,
        ):
            return "hold"
        action = recent_return_gate(
            action,
            closes,
            context_bars=self.context_bars,
            buy_min_recent_return=self.buy_min_recent_return,
            sell_max_recent_return=self.sell_max_recent_return,
        )
        action = apply_intrahour_context(
            action,
            bar,
            buy_min_fine_last_5m=self.buy_min_fine_last_5m,
            sell_max_fine_last_5m=self.sell_max_fine_last_5m,
        )
        if action != "hold":
            self._spec = self._entry.spec_for(action, close)
        return action
