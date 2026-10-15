"""Low-timeframe micro-dip scalper with fixed take-profit/stop and session-end flat."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, SignalAction


class ScalpDipAlgorithm(Algorithm):
    """Buy a micro dip: close ≥ ``dip_pct`` below the highest close of the last ``dip_lookback_bars``
    and the bar closes green (bounce confirmation, not a falling knife). Exit at
    ``take_profit_pct`` / ``stop_loss_pct`` from entry, or flat at ``session_end_hour_utc``
    (−1 = no session). Size is always ``scalp_position_fraction`` of equity — never increased
    after a loss; after a losing trade it waits ``cooldown_bars_after_loss`` bars.
    """

    name = "scalp_dip"
    uses_position_sizing = True

    def __init__(
        self,
        *,
        dip_lookback_bars = 10,
        dip_pct = 0.004,
        take_profit_pct = 0.0075,
        stop_loss_pct = 0.005,
        session_end_hour_utc = -1,
        cooldown_bars_after_loss = 3,
        scalp_position_fraction = 1.0,
    ):
        if dip_lookback_bars < 2:
            raise ValueError("dip_lookback_bars must be >= 2")
        if dip_pct <= 0 or take_profit_pct <= 0 or stop_loss_pct <= 0:
            raise ValueError("dip_pct, take_profit_pct and stop_loss_pct must be positive")
        if not -1 <= session_end_hour_utc <= 23:
            raise ValueError("session_end_hour_utc must be -1 or 0..23")
        if cooldown_bars_after_loss < 0:
            raise ValueError("cooldown_bars_after_loss must be >= 0")
        if not 0 < scalp_position_fraction <= 1:
            raise ValueError("scalp_position_fraction must be in (0, 1]")
        self.dip_lookback_bars = dip_lookback_bars
        self.dip_pct = dip_pct
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.session_end_hour_utc = session_end_hour_utc
        self.cooldown_bars_after_loss = cooldown_bars_after_loss
        self.scalp_position_fraction = scalp_position_fraction
        self.reset()

    def reset(self) -> None:
        self._closes: deque[float] = deque(maxlen=self.dip_lookback_bars)
        self._in_position = False
        self._entry_price = 0.0
        self._cooldown_bars = 0
        self._size: OrderSize | None = None

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._in_position = False

    def order_size(self) -> OrderSize | None:
        return self._size

    def _session_closing(self, bar: Bar) -> bool:
        if self.session_end_hour_utc < 0:
            return False
        hour = datetime.fromtimestamp(int(bar["timestamp"]), tz=timezone.utc).hour
        return hour == self.session_end_hour_utc

    def _exit(self, lost: bool) -> SignalAction:
        self._in_position = False
        self._cooldown_bars = self.cooldown_bars_after_loss if lost else 0
        self._size = OrderSize(target_exposure=0.0)
        return "sell"

    def on_bar(self, bar: Bar) -> SignalAction:
        open_price = float(bar["open"])
        high = float(bar["high"])
        low = float(bar["low"])
        close = float(bar["close"])
        prior_closes = list(self._closes)
        self._closes.append(close)
        self._size = None
        session_closing = self._session_closing(bar)

        if self._in_position:
            if low <= self._entry_price * (1 - self.stop_loss_pct):
                return self._exit(lost=True)
            if high >= self._entry_price * (1 + self.take_profit_pct):
                return self._exit(lost=False)
            if session_closing:
                return self._exit(lost=close < self._entry_price)
            return "hold"

        if self._cooldown_bars > 0:
            self._cooldown_bars -= 1
            return "hold"
        if session_closing or len(prior_closes) < self.dip_lookback_bars - 1:
            return "hold"
        recent_high = max(prior_closes)
        dipped = close <= recent_high * (1 - self.dip_pct)
        if dipped and close > open_price:
            self._in_position = True
            self._entry_price = close
            self._size = OrderSize(target_exposure=self.scalp_position_fraction)
            return "buy"
        return "hold"
