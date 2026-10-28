from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, OrderSpec, SignalAction
from traderbot.algorithms.entry_orders import MakerEntry
from traderbot.algorithms.price_context import apply_mean_reversion_context, signal_clears_cost
from traderbot.algorithms.signals import signal_from_thresholds
from traderbot.algorithms.validators import (
    validate_cost_edge,
    validate_price_context,
    validate_rsi_bands,
)
from traderbot.algorithms.streaming import rsi_init, rsi_reset, rsi_update


class RsiThresholdAlgorithm(Algorithm):
    """Buy when RSI is oversold; sell when overbought.

    ``min_edge_over_cost`` requires the close to sit that multiple of the roundtrip friction
    away from its ``period``-bar mean (the reversion target) before an oversold/overbought
    reading is traded.
    """

    name = "rsi_threshold"

    def __init__(
        self,
        *,
        period = 14,
        oversold = 30.0,
        overbought = 70.0,
        context_bars = 0,
        buy_min_recent_return = -0.03,
        sell_max_recent_return = 0.03,
        buy_min_fine_last_5m: float | None = None,
        sell_max_fine_last_5m: float | None = None,
        min_edge_over_cost: float | None = None,
        roundtrip_cost_pct: float | None = None,
        entry_order_mode: str = "market",
        entry_offset_pct: float = 0.0002,
        entry_ttl_bars: int = 2,
    ):
        validate_rsi_bands(period, oversold, overbought)
        validate_price_context(context_bars, buy_min_recent_return, sell_max_recent_return)
        validate_cost_edge(min_edge_over_cost, roundtrip_cost_pct)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
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
        self._recent: deque[float] = deque(maxlen=period)
        self._rsi = rsi_init(period)
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
        self._recent.clear()
        rsi_reset(self._rsi)
        self._spec = None

    def _mean_close(self) -> float | None:
        if len(self._recent) < self.period:
            return None
        return sum(self._recent) / len(self._recent)

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._closes.append(close)
        self._recent.append(close)
        self._spec = None
        current = rsi_update(self._rsi, close)
        action = signal_from_thresholds(
            current,
            buy_at_or_below=self.oversold,
            sell_at_or_above=self.overbought,
        )
        if action != "hold":
            mean_close = self._mean_close()
            edge_pct = abs(mean_close - close) / close if mean_close is not None and close > 0 else None
            if not signal_clears_cost(
                edge_pct,
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
