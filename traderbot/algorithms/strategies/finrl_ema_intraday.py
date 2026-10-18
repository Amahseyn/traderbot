"""FinRL-Trading intraday preset: EMA 12/48 (Hyperliquid 1m/5m research default)."""

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.signals import signal_from_cross
from traderbot.algorithms.streaming import ema_init, ema_reset, ema_update
from traderbot.algorithms.validators import validate_fast_slow


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
    ):
        validate_fast_slow(fast, slow)
        if signal_style not in ("level_lag", "cross"):
            raise ValueError("signal_style must be 'level_lag' or 'cross'")
        self.fast = fast
        self.slow = slow
        self.price_confirm = price_confirm
        self.signal_style = signal_style
        self._fast = ema_init(fast)
        self._slow = ema_init(slow)
        self._prev_fast: float | None = None
        self._prev_slow: float | None = None
        self._prev_want_long: bool | None = None
        self._held_long = False

    def reset(self) -> None:
        ema_reset(self._fast)
        ema_reset(self._slow)
        self._prev_fast = None
        self._prev_slow = None
        self._prev_want_long = None
        self._held_long = False

    def on_bar(self, bar: Bar) -> SignalAction:
        if self.signal_style == "cross":
            return self._on_bar_cross(bar)
        return self._on_bar_level_lag(bar)

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
