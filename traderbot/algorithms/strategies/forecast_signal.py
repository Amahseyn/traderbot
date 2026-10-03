from collections.abc import Mapping

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.forecast_gate import forecast_direction_signal


class ForecastSignalAlgorithm(Algorithm):
    """Long / flat / short from precomputed holdout forecast log-returns by bar timestamp."""

    name = "forecast_signal"

    def __init__(
        self,
        *,
        forecast_by_timestamp: Mapping[int, float],
        forecast_threshold = 0.0,
    ):
        self._forecast_by_timestamp = dict(forecast_by_timestamp)
        self.forecast_threshold = forecast_threshold

    def reset(self) -> None:
        pass

    def on_bar(self, bar: Bar) -> SignalAction:
        timestamp = int(bar["timestamp"])
        predicted = self._forecast_by_timestamp.get(timestamp)
        return forecast_direction_signal(
            predicted,
            forecast_threshold=self.forecast_threshold,
        )
