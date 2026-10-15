"""Moving-average trend following: price/MA or golden/death cross with pyramiding and trailing stop."""

from __future__ import annotations

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, SignalAction
from traderbot.algorithms.streaming import (
    ema_init,
    ema_reset,
    ema_update,
    rolling_mean_init,
    rolling_mean_reset,
    rolling_mean_update,
)
from traderbot.algorithms.validators import validate_fast_slow

MA_KINDS = ("sma", "ema")
ENTRY_MODES = ("golden_cross", "price_cross")


class MaTrendAlgorithm(Algorithm):
    """Long-only trend follower (e.g. 50/200 golden cross).

    Entry: ``golden_cross`` (fast MA crosses above slow MA) or ``price_cross`` (close
    crosses above the slow MA). Exit: close below the slow MA, a death cross, or the
    trailing stop. While in the trend, a retracement that touches the fast MA and closes
    back above it adds one tranche (up to ``trend_max_adds``).
    """

    name = "ma_trend"
    uses_position_sizing = True

    def __init__(
        self,
        *,
        trend_fast_period = 50,
        trend_slow_period = 200,
        ma_kind = "sma",
        ma_entry_mode = "golden_cross",
        trailing_stop_pct = 0.0,
        trend_max_adds = 0,
    ):
        validate_fast_slow(trend_fast_period, trend_slow_period)
        if ma_kind not in MA_KINDS:
            raise ValueError(f"ma_kind must be one of {MA_KINDS}")
        if ma_entry_mode not in ENTRY_MODES:
            raise ValueError(f"ma_entry_mode must be one of {ENTRY_MODES}")
        if not 0.0 <= trailing_stop_pct < 1.0:
            raise ValueError("trailing_stop_pct must be in [0, 1)")
        if trend_max_adds < 0:
            raise ValueError("trend_max_adds must be >= 0")
        self.trend_fast_period = trend_fast_period
        self.trend_slow_period = trend_slow_period
        self.ma_kind = ma_kind
        self.ma_entry_mode = ma_entry_mode
        self.trailing_stop_pct = trailing_stop_pct
        self.trend_max_adds = trend_max_adds
        self._build_state()

    def _build_state(self) -> None:
        if self.ma_kind == "ema":
            self._fast_state = ema_init(self.trend_fast_period)
            self._slow_state = ema_init(self.trend_slow_period)
        else:
            self._fast_state = rolling_mean_init(self.trend_fast_period)
            self._slow_state = rolling_mean_init(self.trend_slow_period)
        self._bar_count = 0
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None
        self._prev_close: float | None = None
        self._in_position = False
        self._adds = 0
        self._peak_close = 0.0
        self._size: OrderSize | None = None

    def reset(self) -> None:
        if self.ma_kind == "ema":
            ema_reset(self._fast_state)
            ema_reset(self._slow_state)
        else:
            rolling_mean_reset(self._fast_state)
            rolling_mean_reset(self._slow_state)
        self._build_state()

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._in_position = False
            self._adds = 0

    def order_size(self) -> OrderSize | None:
        return self._size

    def _update_averages(self, close: float) -> tuple[float | None, float | None]:
        self._bar_count += 1
        if self.ma_kind == "ema":
            fast = ema_update(self._fast_state, close)
            slow = ema_update(self._slow_state, close)
            if self._bar_count < self.trend_slow_period:
                return None, None
            return fast, slow
        return rolling_mean_update(self._fast_state, close), rolling_mean_update(self._slow_state, close)

    def _tranche_exposure(self, adds: int) -> float:
        return (adds + 1) / (self.trend_max_adds + 1)

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        low = float(bar["low"])
        fast, slow = self._update_averages(close)
        prev_fast, prev_slow, prev_close = self._prev_fast, self._prev_slow, self._prev_close
        self._prev_fast, self._prev_slow, self._prev_close = fast, slow, close
        self._size = None
        if fast is None or slow is None or prev_fast is None or prev_slow is None or prev_close is None:
            return "hold"

        if self._in_position:
            self._peak_close = max(self._peak_close, close)
            trailing_hit = (
                self.trailing_stop_pct > 0 and close <= self._peak_close * (1.0 - self.trailing_stop_pct)
            )
            death_cross = prev_fast >= prev_slow and fast < slow
            if close < slow or death_cross or trailing_hit:
                self._in_position = False
                self._adds = 0
                self._size = OrderSize(target_exposure=0.0)
                return "sell"
            retraced = low <= fast < close and fast > slow
            if retraced and self._adds < self.trend_max_adds:
                self._adds += 1
                self._size = OrderSize(target_exposure=self._tranche_exposure(self._adds))
                return "buy"
            return "hold"

        if self.ma_entry_mode == "golden_cross":
            entered = prev_fast <= prev_slow and fast > slow and close > slow
        else:
            entered = prev_close <= prev_slow and close > slow and fast > slow
        if entered:
            self._in_position = True
            self._adds = 0
            self._peak_close = close
            self._size = OrderSize(target_exposure=self._tranche_exposure(0))
            return "buy"
        return "hold"
