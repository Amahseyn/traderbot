"""Per-round-trip statistics: net average per trade and a t-statistic for significance."""

from __future__ import annotations

import math
from typing import Any

#: Default minimum trades (fills) before a research combo is eligible for ranking.
DEFAULT_MIN_TRADES = 30

#: |t| at or above this counts as statistically meaningful (~95% two-sided for n >= 30).
SIGNIFICANT_T_STAT = 2.0


def round_trip_returns(result: Any) -> list[float]:
    """Net return of each flat -> position -> flat cycle (fees and slippage included).

    Measured on equity: ``equity after the closing fill / equity before the opening fill - 1``,
    so it works for longs, shorts, partial scaling and maker/taker mixes alike.
    """
    returns: list[float] = []
    open_equity: float | None = None
    previous_position = 0.0
    previous_equity = float(result.initial_cash)
    for trade in result.trades:
        before = float(trade.cash_before) + previous_position * float(trade.price)
        if previous_position == 0.0 and trade.position_after != 0.0:
            open_equity = before if before > 0 else previous_equity
        if trade.position_after == 0.0 and open_equity:
            returns.append(float(trade.equity_after) / open_equity - 1.0)
            open_equity = None
        previous_position = float(trade.position_after)
        previous_equity = float(trade.equity_after)
    return returns


def trade_stats(result: Any) -> dict[str, Any]:
    returns = round_trip_returns(result)
    n = len(returns)
    if n == 0:
        return {"round_trips": 0, "avg_trade_net_pct": None, "trade_t_stat": None, "trade_win_rate": None}
    mean = sum(returns) / n
    if n > 1:
        variance = sum((r - mean) ** 2 for r in returns) / (n - 1)
        std = math.sqrt(variance)
        t_stat = mean / (std / math.sqrt(n)) if std > 0 else (math.inf if mean > 0 else -math.inf if mean < 0 else 0.0)
    else:
        t_stat = None
    return {
        "round_trips": n,
        "avg_trade_net_pct": round(mean * 100.0, 6),
        "trade_t_stat": None if t_stat is None or math.isinf(t_stat) else round(t_stat, 4),
        "trade_win_rate": round(sum(1 for r in returns if r > 0) / n, 6),
    }


def edge_rank_key(row: dict[str, Any]) -> tuple[int, int, float, float]:
    """Eligible first, then significant positive edge, then net average per trade, then return."""
    avg = row.get("avg_trade_net_pct")
    t_stat = row.get("trade_t_stat")
    significant = 1 if (t_stat is not None and float(t_stat) >= SIGNIFICANT_T_STAT) else 0
    return (
        1 if row.get("eligible") else 0,
        significant,
        float(avg) if avg is not None else float("-inf"),
        float(row.get("return_pct") or float("-inf")),
    )
