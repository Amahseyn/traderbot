from __future__ import annotations

from traderbot.algorithms.base import SignalAction


def combine_forecast_with_rule_signal(
    rule_action: SignalAction,
    forecast_log_return: float | None,
    *,
    gate_mode: str,
    forecast_threshold: float,
) -> SignalAction:
    """Return ``buy`` / ``sell`` / ``hold`` for ML + rule combination."""
    if forecast_log_return is None:
        return "hold"
    forecast_bull = forecast_log_return > forecast_threshold
    forecast_bear = forecast_log_return < -forecast_threshold
    if gate_mode == "forecast_filters_rule":
        if rule_action == "buy" and forecast_bull:
            return "buy"
        if rule_action == "sell" and forecast_bear:
            return "sell"
        return "hold"
    if gate_mode == "rule_filters_forecast":
        if forecast_bull and rule_action == "buy":
            return "buy"
        if forecast_bear and rule_action == "sell":
            return "sell"
        return "hold"
    raise ValueError(f"unsupported gate_mode={gate_mode!r}")


def forecast_direction_signal(
    forecast_log_return: float | None,
    *,
    forecast_threshold: float,
) -> SignalAction:
    if forecast_log_return is None:
        return "hold"
    if forecast_log_return > forecast_threshold:
        return "buy"
    if forecast_log_return < -forecast_threshold:
        return "sell"
    return "hold"
