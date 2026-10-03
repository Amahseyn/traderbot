from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.signals import signal_from_levels
from traderbot.algorithms.streaming import rolling_mean_init, rolling_mean_reset, rolling_mean_update
from traderbot.algorithms.validators import validate_fast_slow


class SmaCrossAlgorithm(Algorithm):
    """Go long when fast SMA is above slow SMA; flat when below."""

    name = "sma_cross"

    def __init__(self, *, fast = 5, slow = 20, price_confirm = False):
        validate_fast_slow(fast, slow)
        self.fast = fast
        self.slow = slow
        self.price_confirm = price_confirm
        self._fast = rolling_mean_init(fast)
        self._slow = rolling_mean_init(slow)

    def reset(self) -> None:
        rolling_mean_reset(self._fast)
        rolling_mean_reset(self._slow)

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        fast_v = rolling_mean_update(self._fast, close)
        slow_v = rolling_mean_update(self._slow, close)
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
