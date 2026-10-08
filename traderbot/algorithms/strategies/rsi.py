from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.price_context import apply_mean_reversion_context
from traderbot.algorithms.signals import signal_from_thresholds
from traderbot.algorithms.validators import validate_price_context, validate_rsi_bands
from traderbot.algorithms.streaming import rsi_init, rsi_reset, rsi_update


class RsiThresholdAlgorithm(Algorithm):
    """Buy when RSI is oversold; sell when overbought."""

    name = "rsi_threshold"

    def __init__(
        self,
        *,
        period = 14,
        oversold = 30.0,
        overbought = 70.0,
        context_bars = 0,
        buy_min_recent_return = -0.03,
        sell_max_recent_return = 0.03,
        buy_min_fine_last_5m: float | None = None,
        sell_max_fine_last_5m: float | None = None,
    ):
        validate_rsi_bands(period, oversold, overbought)
        validate_price_context(context_bars, buy_min_recent_return, sell_max_recent_return)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.context_bars = context_bars
        self.buy_min_recent_return = buy_min_recent_return
        self.sell_max_recent_return = sell_max_recent_return
        self.buy_min_fine_last_5m = buy_min_fine_last_5m
        self.sell_max_fine_last_5m = sell_max_fine_last_5m
        self._closes: list[float] = []
        self._rsi = rsi_init(period)

    def reset(self) -> None:
        self._closes.clear()
        rsi_reset(self._rsi)

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._closes.append(close)
        current = rsi_update(self._rsi, close)
        action = signal_from_thresholds(
            current,
            buy_at_or_below=self.oversold,
            sell_at_or_above=self.overbought,
        )
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
