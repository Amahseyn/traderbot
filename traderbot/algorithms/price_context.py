from __future__ import annotations

from traderbot.algorithms.base import SignalAction


def recent_cumulative_return(closes: list[float], context_bars: int) -> float | None:
    """Total simple return over the last ``context_bars`` bars ending at the latest close."""
    if context_bars < 1 or len(closes) < context_bars + 1:
        return None
    start = closes[-(context_bars + 1)]
    end = closes[-1]
    if start <= 0:
        return None
    return end / start - 1.0


def mean_reversion_buy_allowed(
    closes: list[float],
    *,
    context_bars: int,
    buy_min_recent_return: float,
) -> bool:
    if context_bars <= 0:
        return True
    ret = recent_cumulative_return(closes, context_bars)
    if ret is None:
        return False
    return ret >= buy_min_recent_return


def mean_reversion_sell_allowed(
    closes: list[float],
    *,
    context_bars: int,
    sell_max_recent_return: float,
) -> bool:
    if context_bars <= 0:
        return True
    ret = recent_cumulative_return(closes, context_bars)
    if ret is None:
        return False
    return ret <= sell_max_recent_return


def apply_mean_reversion_context(
    action: SignalAction,
    closes: list[float],
    *,
    context_bars: int,
    buy_min_recent_return: float,
    sell_max_recent_return: float,
) -> SignalAction:
    if action == "buy" and not mean_reversion_buy_allowed(
        closes,
        context_bars=context_bars,
        buy_min_recent_return=buy_min_recent_return,
    ):
        return "hold"
    if action == "sell" and not mean_reversion_sell_allowed(
        closes,
        context_bars=context_bars,
        sell_max_recent_return=sell_max_recent_return,
    ):
        return "hold"
    return action
