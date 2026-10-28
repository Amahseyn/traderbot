from traderbot.algorithms.base import Algorithm, Bar, OrderSpec, SignalAction
from traderbot.algorithms.entry_orders import MakerEntry
from traderbot.algorithms.price_context import (
    apply_mean_reversion_context,
    recent_cumulative_return,
    trend_edge_window_bars,
    trend_signal_clears_cost,
)
from traderbot.algorithms.signals import signal_from_cross
from traderbot.algorithms.validators import validate_cost_edge, validate_macd, validate_price_context
from traderbot.algorithms.streaming import macd_init, macd_reset, macd_update


class MacdCrossAlgorithm(Algorithm):
    """Enter long on MACD line crossing above signal; flat on cross below.

    The MACD line sits at zero on the crossing bar, so the momentum gate measures the recent
    price move over ``context_bars`` (or ``slow`` bars when that filter is off) and requires it
    to clear ``min_edge_over_cost`` x the roundtrip friction in the trade's direction.
    """

    name = "macd_cross"

    def __init__(
        self,
        *,
        fast = 12,
        slow = 26,
        signal = 9,
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
        validate_macd(fast, slow, signal)
        validate_price_context(context_bars, buy_min_recent_return, sell_max_recent_return)
        validate_cost_edge(min_edge_over_cost, roundtrip_cost_pct)
        self.fast = fast
        self.slow = slow
        self.signal = signal
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
        self._closes: list[float] = []
        self._macd = macd_init(self.fast, self.slow, self.signal)
        self._prev_line: float | None = None
        self._prev_sig: float | None = None
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
        self._closes.clear()
        macd_reset(self._macd)
        self._prev_line = None
        self._prev_sig = None
        self._spec = None

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._closes.append(close)
        self._spec = None
        line, sig, _hist = macd_update(self._macd, close)
        action = signal_from_cross(self._prev_line, self._prev_sig, line, sig)
        self._prev_line = line
        self._prev_sig = sig
        if action != "hold":
            window_bars = trend_edge_window_bars(self.context_bars, self.slow)
            move_pct = recent_cumulative_return(self._closes, window_bars)
            if not trend_signal_clears_cost(
                action,
                move_pct,
                roundtrip_cost_pct=self.roundtrip_cost_pct,
                min_edge_over_cost=self.min_edge_over_cost,
            ):
                return "hold"
        action = apply_mean_reversion_context(
            action,
            self._closes,
            context_bars=self.context_bars,
            buy_min_recent_return=self.buy_min_recent_return,
            sell_max_recent_return=self.sell_max_recent_return,
            bar=bar,
            buy_min_fine_last_5m=self.buy_min_fine_last_5m,
            sell_max_fine_last_5m=self.sell_max_fine_last_5m,
        )
        if action != "hold":
            self._spec = self._entry.spec_for(action, close)
        return action
