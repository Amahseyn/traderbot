from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, SignalAction
from traderbot.algorithms.position_sizing import EntryTranches
from traderbot.algorithms.price_context import signal_clears_cost
from traderbot.algorithms.streaming import atr_init, atr_reset, atr_update
from traderbot.algorithms.validators import validate_cost_edge


class BreakoutAtrAlgorithm(Algorithm):
    """Enter long on close above recent high + ATR buffer; exit on breakdown or ATR stop.

    While long, a fresh breakout bar can add another tranche when ``max_tranches > 1``
    (after ``tranche_gap_bars`` bars); the ATR stop is re-anchored on the newer close.
    """

    name = "breakout_atr"

    def __init__(
        self,
        *,
        lookback_bars = 20,
        atr_period = 14,
        atr_multiplier = 1.5,
        stop_atr_multiplier = 1.0,
        min_edge_over_cost: float | None = None,
        roundtrip_cost_pct: float | None = None,
        target_exposure: float = 1.0,
        max_tranches: int = 1,
        tranche_gap_bars: int = 0,
    ):
        if lookback_bars < 2:
            raise ValueError("lookback_bars must be >= 2")
        if atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if atr_multiplier <= 0:
            raise ValueError("atr_multiplier must be positive")
        if stop_atr_multiplier <= 0:
            raise ValueError("stop_atr_multiplier must be positive")
        validate_cost_edge(min_edge_over_cost, roundtrip_cost_pct)
        self._entries = EntryTranches(
            target_exposure=target_exposure,
            max_tranches=max_tranches,
            tranche_gap_bars=tranche_gap_bars,
        )
        self.target_exposure = self._entries.target_exposure
        if self._entries.partial:
            self.uses_position_sizing = True
        self.lookback_bars = lookback_bars
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.stop_atr_multiplier = stop_atr_multiplier
        self.min_edge_over_cost = 0.0 if min_edge_over_cost is None else float(min_edge_over_cost)
        self.roundtrip_cost_pct = roundtrip_cost_pct
        self._highs: deque[float] = deque(maxlen=lookback_bars + 1)
        self._lows: deque[float] = deque(maxlen=lookback_bars + 1)
        self._atr = atr_init(atr_period)
        self._in_long = False
        self._stop_price: float | None = None
        self._size: OrderSize | None = None

    def reset(self) -> None:
        self._highs.clear()
        self._lows.clear()
        atr_reset(self._atr)
        self._in_long = False
        self._stop_price = None
        self._size = None
        self._entries.reset()

    def order_size(self) -> OrderSize | None:
        return self._size

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._in_long = False
            self._stop_price = None
            self._entries.reset()

    def _breakout_clears_cost(self, atr_now: float, close: float) -> bool:
        edge_pct = (self.atr_multiplier * atr_now) / close if close > 0 else 0.0
        return signal_clears_cost(
            edge_pct,
            roundtrip_cost_pct=self.roundtrip_cost_pct,
            min_edge_over_cost=self.min_edge_over_cost,
        )

    def on_bar(self, bar: Bar) -> SignalAction:
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        self._entries.tick()
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
        breakout = close > upper_break and self._breakout_clears_cost(atr_now, close)

        if self._in_long:
            if self._stop_price is not None and low <= self._stop_price:
                self._in_long = False
                self._stop_price = None
                self._size = self._entries.note_exit()
                return "sell"
            if close < lower_break:
                self._in_long = False
                self._stop_price = None
                self._size = self._entries.note_exit()
                return "sell"
            if breakout and self._entries.allows_entry():
                self._stop_price = close - self.stop_atr_multiplier * atr_now
                self._size = self._entries.note_entry()
                return "buy"
            return "hold"

        if breakout:
            self._in_long = True
            self._stop_price = close - self.stop_atr_multiplier * atr_now
            self._size = self._entries.note_entry()
            return "buy"
        return "hold"
