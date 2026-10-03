from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.price_context import apply_mean_reversion_context
from traderbot.algorithms.signals import signal_from_cross
from traderbot.algorithms.validators import validate_macd, validate_price_context
from traderbot.ml.features import macd


class MacdCrossAlgorithm(Algorithm):
    """Enter long on MACD line crossing above signal; flat on cross below."""

    name = "macd_cross"

    def __init__(
        self,
        *,
        fast = 12,
        slow = 26,
        signal = 9,
        context_bars = 0,
        buy_min_recent_return = -0.03,
        sell_max_recent_return = 0.03,
        buy_min_fine_last_5m: float | None = None,
        sell_max_fine_last_5m: float | None = None,
    ):
        validate_macd(fast, slow, signal)
        validate_price_context(context_bars, buy_min_recent_return, sell_max_recent_return)
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.context_bars = context_bars
        self.buy_min_recent_return = buy_min_recent_return
        self.sell_max_recent_return = sell_max_recent_return
        self.buy_min_fine_last_5m = buy_min_fine_last_5m
        self.sell_max_fine_last_5m = sell_max_fine_last_5m
        self._closes: list[float] = []

    def reset(self) -> None:
        self._closes.clear()

    def on_bar(self, bar: Bar) -> SignalAction:
        self._closes.append(float(bar["close"]))
        line, sig, _hist = macd(
            self._closes,
            fast=self.fast,
            slow=self.slow,
            signal=self.signal,
        )
        i = len(self._closes) - 1
        if i < 1:
            return "hold"
        action = signal_from_cross(line[i - 1], sig[i - 1], line[i], sig[i])
        return apply_mean_reversion_context(
            action,
            self._closes,
            context_bars=self.context_bars,
            buy_min_recent_return=self.buy_min_recent_return,
            sell_max_recent_return=self.sell_max_recent_return,
            bar=bar,
            buy_min_fine_last_5m=self.buy_min_fine_last_5m,
            sell_max_fine_last_5m=self.sell_max_fine_last_5m,
        )
