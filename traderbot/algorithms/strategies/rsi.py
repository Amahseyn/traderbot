from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.price_context import apply_mean_reversion_context
from traderbot.algorithms.signals import signal_from_thresholds
from traderbot.algorithms.validators import validate_price_context, validate_rsi_bands
from traderbot.ml.features import rsi


class RsiThresholdAlgorithm(Algorithm):
    """Buy when RSI is oversold; sell when overbought."""

    name = "rsi_threshold"

    def __init__(
        self,
        *,
        period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        context_bars: int = 0,
        buy_min_recent_return: float = -0.03,
        sell_max_recent_return: float = 0.03,
    ):
        validate_rsi_bands(period, oversold, overbought)
        validate_price_context(context_bars, buy_min_recent_return, sell_max_recent_return)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
        self.context_bars = context_bars
        self.buy_min_recent_return = buy_min_recent_return
        self.sell_max_recent_return = sell_max_recent_return
        self._closes: list[float] = []

    def reset(self) -> None:
        self._closes.clear()

    def on_bar(self, bar: Bar) -> SignalAction:
        self._closes.append(float(bar["close"]))
        current = rsi(self._closes, period=self.period)[-1]
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
        )
