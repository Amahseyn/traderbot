from collections import deque

from traderbot.algorithms.bands import bollinger_init, bollinger_reset, bollinger_update
from traderbot.algorithms.base import Algorithm, Bar, OrderSpec, SignalAction
from traderbot.algorithms.entry_orders import MakerEntry
from traderbot.algorithms.price_context import apply_mean_reversion_context, signal_clears_cost
from traderbot.algorithms.validators import validate_bollinger, validate_cost_edge, validate_price_context


class BollingerMeanReversionAlgorithm(Algorithm):
    """Buy at the lower Bollinger band; sell at the upper band.

    ``min_edge_over_cost`` requires the distance from the close to the band **mean** — the
    reversion the entry is betting on — to cover that multiple of the roundtrip friction
    (0.19% on Hyperliquid taker). On 1-minute bars the bands sit well inside the cost, so the
    gate is what keeps the strategy from paying 0.19% to capture 0.04%.
    """

    name = "bollinger_mean_reversion"

    def __init__(
        self,
        *,
        period = 20,
        num_std = 2.0,
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
        validate_bollinger(period, num_std)
        validate_price_context(context_bars, buy_min_recent_return, sell_max_recent_return)
        validate_cost_edge(min_edge_over_cost, roundtrip_cost_pct)
        self.period = period
        self.num_std = num_std
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
        self._bands = bollinger_init(period=period, num_std=num_std)
        close_history = max(period, context_bars + 1, 1)
        self._closes: deque[float] = deque(maxlen=close_history)
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
        bollinger_reset(self._bands)
        self._closes.clear()
        self._spec = None

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._closes.append(close)
        self._spec = None
        levels = bollinger_update(self._bands, close)
        if levels is None:
            return "hold"
        lower, upper, mean = levels
        if close <= lower:
            action = "buy"
        elif close >= upper:
            action = "sell"
        else:
            return "hold"
        # Distance to the band mean is the move the reversion trade is aiming at.
        edge_pct = abs(mean - close) / close if close > 0 else None
        if not signal_clears_cost(
            edge_pct,
            roundtrip_cost_pct=self.roundtrip_cost_pct,
            min_edge_over_cost=self.min_edge_over_cost,
        ):
            return "hold"
        action = apply_mean_reversion_context(
            action,
            list(self._closes),
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
