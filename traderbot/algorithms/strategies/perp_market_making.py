"""
Maker quoting strategy for Hyperliquid perps (inspired by Hummingbot PMM).

Quotes are computed at bar *t*'s close and rest during bar *t+1*, so nothing uses the bar
it fills on. Backtests fill a quote only when the next bar trades **through** it, at the
quote price, paying the maker fee (Hyperliquid tier 0: 0.015%). Live, quotes are post-only
(ALO) resting limits that the trader cancels/replaces every bar.

* **Spread**: ``half_spread_pct`` around the reference (last close), widened to
  ``vol_spread_mult`` x the recent ATR% when volatility is higher.
* **Inventory skew**: the reservation price shifts by ``inventory_skew`` x half-spread
  against the current position, so a long quotes a cheaper ask (exits sooner).
* **Adverse-selection guard**: no new entries after a bar move larger than
  ``adverse_move_atr`` x ATR in the direction that would be bought into, and while the
  short-term EMA slope runs against the entry; open positions carry a protective stop
  (``stop_loss_pct``, taker) and the exit ask never sits below entry + ``min_profit_pct``.
* ``allow_short``: quote an ask to open shorts when flat (perps only).
"""

from __future__ import annotations

from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, Quote, SignalAction
from traderbot.algorithms.streaming import atr_init, atr_update, ema_init, ema_update


class PerpMarketMakingAlgorithm(Algorithm):
    name = "perp_market_making"
    uses_position_sizing = True

    def __init__(
        self,
        *,
        half_spread_pct: float = 0.0005,
        inventory_skew: float = 0.0,
        vol_spread_mult: float = 0.5,
        atr_period: int = 14,
        adverse_move_atr: float = 2.0,
        trend_ema_period: int = 20,
        stop_loss_pct: float = 0.004,
        min_profit_pct: float = 0.0004,
        order_fraction: float = 1.0,
        allow_short: bool = False,
        trend_guard: bool = True,
    ):
        if half_spread_pct <= 0:
            raise ValueError("half_spread_pct must be positive")
        if not 0 <= inventory_skew <= 1:
            raise ValueError("inventory_skew must be in [0, 1]")
        if vol_spread_mult < 0 or adverse_move_atr < 0 or min_profit_pct < 0:
            raise ValueError("vol_spread_mult, adverse_move_atr and min_profit_pct must be >= 0")
        if stop_loss_pct < 0:
            raise ValueError("stop_loss_pct must be >= 0 (0 = no stop)")
        if not 0 < order_fraction <= 1:
            raise ValueError("order_fraction must be in (0, 1]")
        if atr_period < 1 or trend_ema_period < 2:
            raise ValueError("atr_period must be >= 1 and trend_ema_period >= 2")
        self.half_spread_pct = half_spread_pct
        self.inventory_skew = inventory_skew
        self.vol_spread_mult = vol_spread_mult
        self.atr_period = atr_period
        self.adverse_move_atr = adverse_move_atr
        self.trend_ema_period = trend_ema_period
        self.stop_loss_pct = stop_loss_pct
        self.min_profit_pct = min_profit_pct
        self.order_fraction = order_fraction
        self.allow_short = bool(allow_short)
        self.trend_guard = bool(trend_guard)
        self.reset()

    def reset(self) -> None:
        self._atr = atr_init(self.atr_period)
        self._ema = ema_init(self.trend_ema_period)
        self._emas: deque[float] = deque(maxlen=3)
        self._direction = 0  # +1 long, -1 short, 0 flat
        self._entry_price = 0.0
        self._quotes: list[Quote] = []
        self._bars = 0

    # --- position bookkeeping -------------------------------------------------------------

    @property
    def _in_position(self) -> bool:  # kept for older callers / tests
        return self._direction != 0

    def sync_open_position(self, in_position: bool) -> None:
        """Match paper/live inventory after warmup (history replay does not trade)."""
        if not in_position:
            self._direction = 0
            self._entry_price = 0.0
        elif self._direction == 0:
            self._direction = 1

    def on_fill(self, side: str, price: float, size: float, reason: str, position: float) -> None:
        new_direction = 0 if position == 0 else (1 if position > 0 else -1)
        if new_direction != 0 and new_direction != self._direction:
            self._entry_price = price
        if new_direction == 0:
            self._entry_price = 0.0
        self._direction = new_direction

    def quotes(self) -> list[Quote] | None:
        return list(self._quotes)

    # --- quoting --------------------------------------------------------------------------

    def _half_spread(self, close: float, atr: float | None) -> float:
        half = self.half_spread_pct
        if atr and close > 0 and self.vol_spread_mult > 0:
            half = max(half, self.vol_spread_mult * atr / close)
        return half

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        open_price = float(bar.get("open", close))
        high = float(bar.get("high", close))
        low = float(bar.get("low", close))
        atr = atr_update(self._atr, high=high, low=low, close=close)
        ema = ema_update(self._ema, close)
        self._emas.append(ema)
        self._bars += 1
        self._quotes = []
        if close <= 0:
            return "hold"

        half = self._half_spread(close, atr)
        skew = self.inventory_skew * half * self._direction
        reservation = close * (1.0 - skew)
        bid = reservation * (1.0 - half)
        ask = reservation * (1.0 + half)
        stop = self.stop_loss_pct or None

        if self._direction > 0:
            floor = self._entry_price * (1.0 + self.min_profit_pct) if self._entry_price > 0 else 0.0
            self._quotes.append(Quote(side="sell", limit_price=max(ask, floor), target_exposure=0.0))
            return "hold"
        if self._direction < 0:
            cap = self._entry_price * (1.0 - self.min_profit_pct) if self._entry_price > 0 else bid
            self._quotes.append(Quote(side="buy", limit_price=min(bid, cap), target_exposure=0.0))
            return "hold"

        warm = self._bars > max(self.atr_period, 2)
        if not warm:
            return "hold"
        bar_move = close - open_price
        shock = atr is not None and atr > 0 and self.adverse_move_atr > 0 and abs(bar_move) > self.adverse_move_atr * atr
        slope = self._emas[-1] - self._emas[0] if (self.trend_guard and len(self._emas) >= 2) else 0.0
        # Do not buy into a falling knife / sell into a squeeze.
        if not (shock and bar_move < 0) and slope >= 0:
            self._quotes.append(
                Quote(side="buy", limit_price=bid, target_exposure=self.order_fraction, stop_loss_pct=stop)
            )
        if self.allow_short and not (shock and bar_move > 0) and slope <= 0:
            self._quotes.append(
                Quote(side="sell", limit_price=ask, target_exposure=-self.order_fraction, stop_loss_pct=stop)
            )
        return "hold"
