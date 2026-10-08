from __future__ import annotations

from traderbot.algorithms.base import SignalAction


def order_action_for_long_only(in_position: bool, signal: SignalAction) -> SignalAction | None:
    """Map repeating buy/sell signals to at most one fill per leg (matches backtest long-only)."""
    if signal == "buy" and not in_position:
        return "buy"
    if signal == "sell" and in_position:
        return "sell"
    return None
