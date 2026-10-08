from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.price_context import apply_mean_reversion_context
from traderbot.algorithms.signals import signal_from_cross
from traderbot.algorithms.validators import validate_macd, validate_price_context
from traderbot.algorithms.streaming import macd_init, macd_reset, macd_update


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
        self._macd = macd_init(self.fast, self.slow, self.signal)
        self._prev_line: float | None = None
        self._prev_sig: float | None = None

    def reset(self) -> None:
        self._closes.clear()
        macd_reset(self._macd)
        self._prev_line = None
        self._prev_sig = None

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._closes.append(close)
        line, sig, _hist = macd_update(self._macd, close)
        action = signal_from_cross(self._prev_line, self._prev_sig, line, sig)
        self._prev_line = line
        self._prev_sig = sig
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
