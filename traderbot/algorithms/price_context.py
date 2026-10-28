from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from traderbot.algorithms.base import SignalAction
from traderbot.utils.trading_costs import default_roundtrip_cost_pct


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


def resolve_roundtrip_cost_pct(roundtrip_cost_pct: float | None) -> float:
    """``None`` means "the repo default venue" (Hyperliquid perp taker); 0 disables the gate."""
    if roundtrip_cost_pct is None:
        return default_roundtrip_cost_pct()
    return max(0.0, float(roundtrip_cost_pct))


def required_signal_edge_pct(
    roundtrip_cost_pct: float | None,
    min_edge_over_cost: float,
) -> float:
    """Favorable move a signal must plausibly capture before it can pay for a roundtrip.

    ``min_edge_over_cost`` is a multiple of the roundtrip friction: 1.0 is break-even, below
    which the trade is expected to lose money on average no matter how good the entry looks.
    The threshold self-scales by venue (0.19% on Hyperliquid taker, 0.90% on Nobitex) and by
    bar size, so 1-minute signals need a real move while daily ones clear it trivially.
    """
    if min_edge_over_cost <= 0:
        return 0.0
    return float(min_edge_over_cost) * resolve_roundtrip_cost_pct(roundtrip_cost_pct)


def signal_clears_cost(
    edge_pct: float | None,
    *,
    roundtrip_cost_pct: float | None,
    min_edge_over_cost: float,
) -> bool:
    """True when ``edge_pct`` (expected favorable move) covers the required roundtrip edge.

    A signal with no computable edge is rejected once the gate is on: without a target there
    is no way to know the trade can pay for its own friction. Magnitude only — use this for
    mean reversion, where the profitable move runs *against* the recent path.
    """
    required = required_signal_edge_pct(roundtrip_cost_pct, min_edge_over_cost)
    if required <= 0:
        return True
    if edge_pct is None:
        return False
    return abs(float(edge_pct)) >= required


def trend_signal_clears_cost(
    action: SignalAction,
    move_pct: float | None,
    *,
    roundtrip_cost_pct: float | None,
    min_edge_over_cost: float,
) -> bool:
    """Signed variant for trend entries: momentum must clear cost *in the trade direction*.

    A cross that fires on a 0.02% drift cannot pay a 0.19% roundtrip even if it is right, so
    the buy needs ``move_pct >= required`` and the sell ``move_pct <= -required``.
    """
    required = required_signal_edge_pct(roundtrip_cost_pct, min_edge_over_cost)
    if required <= 0:
        return True
    if move_pct is None:
        return False
    if action == "buy":
        return float(move_pct) >= required
    if action == "sell":
        return float(move_pct) <= -required
    return True


def trend_edge_window_bars(context_bars: int, slow_period: int) -> int:
    """Bars used to measure the momentum a cross entry is riding.

    ``context_bars`` when the recent-price filter is on, otherwise the slow average's own
    lookback: a crossover is by construction a statement about roughly that horizon.
    """
    if context_bars > 0:
        return int(context_bars)
    return max(int(slow_period), 1)


def recent_return_gate(
    action: SignalAction,
    closes: list[float],
    *,
    context_bars: int,
    buy_min_recent_return: float,
    sell_max_recent_return: float,
) -> SignalAction:
    """Block entries that disagree with the recent price path.

    Mean reversion passes ``buy_min_recent_return=-0.03`` / ``sell_max_recent_return=0.03`` so a
    buy is not placed into a sharp dump. Trend strategies pass ``0.0`` / ``0.0`` so a cross is
    only traded when the recent path already points that way (momentum confirmation).
    """
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


def apply_intrahour_context(
    action: SignalAction,
    bar: Mapping[str, Any],
    *,
    buy_min_fine_last_5m: float | None = None,
    sell_max_fine_last_5m: float | None = None,
) -> SignalAction:
    """Optional gate using 1m-derived ``fine_return_last_5m`` on enriched coarse bars."""
    if action == "buy" and buy_min_fine_last_5m is not None:
        ret = bar.get("fine_return_last_5m")
        if ret is not None and float(ret) < buy_min_fine_last_5m:
            return "hold"
    if action == "sell" and sell_max_fine_last_5m is not None:
        ret = bar.get("fine_return_last_5m")
        if ret is not None and float(ret) > sell_max_fine_last_5m:
            return "hold"
    return action


def apply_mean_reversion_context(
    action: SignalAction,
    closes: list[float],
    *,
    context_bars: int,
    buy_min_recent_return: float,
    sell_max_recent_return: float,
    bar: Mapping[str, Any] | None = None,
    buy_min_fine_last_5m: float | None = None,
    sell_max_fine_last_5m: float | None = None,
) -> SignalAction:
    action = recent_return_gate(
        action,
        closes,
        context_bars=context_bars,
        buy_min_recent_return=buy_min_recent_return,
        sell_max_recent_return=sell_max_recent_return,
    )
    if bar is not None and action != "hold":
        return apply_intrahour_context(
            action,
            bar,
            buy_min_fine_last_5m=buy_min_fine_last_5m,
            sell_max_fine_last_5m=sell_max_fine_last_5m,
        )
    return action
