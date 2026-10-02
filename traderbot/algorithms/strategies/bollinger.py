from collections import deque

from traderbot.algorithms.bands import bollinger_init, bollinger_reset, bollinger_update
from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.price_context import apply_mean_reversion_context
from traderbot.algorithms.validators import validate_bollinger, validate_price_context


class BollingerMeanReversionAlgorithm(Algorithm):
    """Buy at the lower Bollinger band; sell at the upper band."""

    name = "bollinger_mean_reversion"

    def __init__(
        self,
        *,
        period: int = 20,
        num_std: float = 2.0,
        context_bars: int = 0,
        buy_min_recent_return: float = -0.03,
        sell_max_recent_return: float = 0.03,
    ):
        validate_bollinger(period, num_std)
        validate_price_context(context_bars, buy_min_recent_return, sell_max_recent_return)
        self.period = period
        self.num_std = num_std
        self.context_bars = context_bars
        self.buy_min_recent_return = buy_min_recent_return
        self.sell_max_recent_return = sell_max_recent_return
        self._bands = bollinger_init(period=period, num_std=num_std)
        close_history = max(period, context_bars + 1, 1)
        self._closes: deque[float] = deque(maxlen=close_history)

    def reset(self) -> None:
        bollinger_reset(self._bands)
        self._closes.clear()

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        self._closes.append(close)
        levels = bollinger_update(self._bands, close)
        if levels is None:
            return "hold"
        lower, upper, _mean = levels
        if close <= lower:
            action = "buy"
        elif close >= upper:
            action = "sell"
        else:
            return "hold"
        return apply_mean_reversion_context(
            action,
            list(self._closes),
            context_bars=self.context_bars,
            buy_min_recent_return=self.buy_min_recent_return,
            sell_max_recent_return=self.sell_max_recent_return,
        )
