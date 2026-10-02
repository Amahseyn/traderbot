from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.signals import signal_from_levels
from traderbot.algorithms.streaming import ema_init, ema_reset, ema_update
from traderbot.algorithms.validators import validate_fast_slow


class EmaCrossAlgorithm(Algorithm):
    """Go long when fast EMA is above slow EMA; flat when below."""

    name = "ema_cross"

    def __init__(self, *, fast: int = 12, slow: int = 26, price_confirm: bool = False):
        validate_fast_slow(fast, slow)
        self.fast = fast
        self.slow = slow
        self.price_confirm = price_confirm
        self._fast = ema_init(fast)
        self._slow = ema_init(slow)
        self._bars = 0

    def reset(self) -> None:
        ema_reset(self._fast)
        ema_reset(self._slow)
        self._bars = 0

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._bars += 1
        if self._bars < self.slow:
            ema_update(self._fast, close)
            ema_update(self._slow, close)
            return "hold"
        fast_v = ema_update(self._fast, close)
        slow_v = ema_update(self._slow, close)
        action = signal_from_levels(fast_v, slow_v)
        if not self.price_confirm or action == "hold":
            return action
        if fast_v is None:
            return "hold"
        if action == "buy" and close < fast_v:
            return "hold"
        if action == "sell" and close > fast_v:
            return "hold"
        return action
