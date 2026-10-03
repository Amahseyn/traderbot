from collections.abc import Mapping

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.forecast_gate import combine_forecast_with_rule_signal


class MlGatedAlgorithm(Algorithm):
    """
    Combine a rule strategy with ML holdout forecasts.

    ``forecast_filters_rule``: take rule buys/sells only when the forecast agrees.
    ``rule_filters_forecast``: take forecast direction only when the rule agrees.
    """

    name = "ml_gated"

    def __init__(
        self,
        *,
        inner: Algorithm,
        forecast_by_timestamp: Mapping[int, float],
        gate_mode = "forecast_filters_rule",
        forecast_threshold = 0.0,
    ):
        if gate_mode not in ("forecast_filters_rule", "rule_filters_forecast"):
            raise ValueError("gate_mode must be forecast_filters_rule or rule_filters_forecast")
        self._inner = inner
        self._forecast_by_timestamp = dict(forecast_by_timestamp)
        self.gate_mode = gate_mode
        self.forecast_threshold = forecast_threshold

    def reset(self) -> None:
        self._inner.reset()

    def on_bar(self, bar: Bar) -> SignalAction:
        rule_action = self._inner.on_bar(bar)
        timestamp = int(bar["timestamp"])
        predicted = self._forecast_by_timestamp.get(timestamp)
        return combine_forecast_with_rule_signal(
            rule_action,
            predicted,
            gate_mode=self.gate_mode,
            forecast_threshold=self.forecast_threshold,
        )
