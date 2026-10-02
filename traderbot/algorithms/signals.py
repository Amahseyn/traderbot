from __future__ import annotations

from traderbot.algorithms.base import SignalAction


def signal_from_levels(fast: float | None, slow: float | None) -> SignalAction:
    """Long when ``fast > slow``, flat when ``fast < slow``."""
    if fast is None or slow is None:
        return "hold"
    if fast > slow:
        return "buy"
    if fast < slow:
        return "sell"
    return "hold"


def signal_from_thresholds(
    value: float | None,
    *,
    buy_at_or_below: float,
    sell_at_or_above: float,
) -> SignalAction:
    if value is None:
        return "hold"
    if value <= buy_at_or_below:
        return "buy"
    if value >= sell_at_or_above:
        return "sell"
    return "hold"


def signal_from_cross(
    prev_a: float | None,
    prev_b: float | None,
    cur_a: float | None,
    cur_b: float | None,
) -> SignalAction:
    """Buy when ``a`` crosses above ``b``; sell when ``a`` crosses below ``b``."""
    if prev_a is None or prev_b is None or cur_a is None or cur_b is None:
        return "hold"
    if prev_a <= prev_b and cur_a > cur_b:
        return "buy"
    if prev_a >= prev_b and cur_a < cur_b:
        return "sell"
    return "hold"
