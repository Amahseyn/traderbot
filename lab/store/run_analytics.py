"""Trade-level analytics for a stored strategy backtest (from ``trade_logs``)."""

from __future__ import annotations

import math
from typing import Any

MAX_CURVE_POINTS = 1000
POSITION_EPSILON = 1e-12


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _round(value: float | None, digits: int = 6) -> float | None:
    return None if value is None or not math.isfinite(value) else round(value, digits)


def _downsample(points: list[dict[str, Any]], limit: int = MAX_CURVE_POINTS) -> list[dict[str, Any]]:
    if len(points) <= limit:
        return points
    step = (len(points) - 1) / (limit - 1)
    return [points[round(index * step)] for index in range(limit)]


def _ratio(values: list[float], downside_only: bool) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if downside_only:
        downside = [min(value, 0.0) ** 2 for value in values]
        deviation = math.sqrt(sum(downside) / len(values))
    else:
        deviation = math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))
    if deviation <= 0:
        return None
    return mean / deviation * math.sqrt(len(values))


def _round_trips(logs: list[dict[str, Any]], initial_cash: float) -> list[dict[str, Any]]:
    """Group fills into flat → open → flat cycles; PnL is the equity change (fees included)."""
    trips: list[dict[str, Any]] = []
    position = 0.0
    equity_before = initial_cash
    current: dict[str, Any] | None = None
    for fill in logs:
        equity_after = _number(fill.get("equity_after"))
        position_after = _number(fill.get("position_after")) or 0.0
        timestamp = _number(fill.get("timestamp"))
        if current is None and abs(position) <= POSITION_EPSILON and abs(position_after) > POSITION_EPSILON:
            current = {
                "side": "long" if position_after > 0 else "short",
                "entry_timestamp": timestamp,
                "entry_price": _number(fill.get("price")),
                "entry_equity": equity_before,
                "fills": 0,
            }
        if current is not None:
            current["fills"] += 1
            if abs(position_after) <= POSITION_EPSILON and equity_after is not None:
                pnl = equity_after - current["entry_equity"]
                entry_equity = current["entry_equity"]
                trips.append(
                    {
                        **current,
                        "exit_timestamp": timestamp,
                        "exit_price": _number(fill.get("price")),
                        "pnl": pnl,
                        "return_pct": pnl / entry_equity * 100 if entry_equity else None,
                        "duration_seconds": (
                            timestamp - current["entry_timestamp"]
                            if timestamp is not None and current["entry_timestamp"] is not None
                            else None
                        ),
                    }
                )
                current = None
        position = position_after
        if equity_after is not None:
            equity_before = equity_after
    return trips


def _streaks(pnls: list[float]) -> tuple[int, int]:
    best_win = best_loss = win = loss = 0
    for pnl in pnls:
        if pnl > 0:
            win, loss = win + 1, 0
        elif pnl < 0:
            win, loss = 0, loss + 1
        else:
            win = loss = 0
        best_win, best_loss = max(best_win, win), max(best_loss, loss)
    return best_win, best_loss


def compute_run_analytics(metrics: dict[str, Any]) -> dict[str, Any]:
    raw_logs = metrics.get("trade_logs")
    logs = [entry for entry in raw_logs if isinstance(entry, dict)] if isinstance(raw_logs, list) else []
    cash_flow = metrics.get("cash_flow") if isinstance(metrics.get("cash_flow"), dict) else {}
    initial_cash = _number(metrics.get("initial_cash")) or _number(cash_flow.get("initial_cash"))
    final_equity = _number(metrics.get("final_equity")) or _number(cash_flow.get("final_equity"))
    if initial_cash is None and logs:
        first = logs[0]
        initial_cash = _number(first.get("cash_before"))
    initial_cash = initial_cash or 0.0

    curve: list[dict[str, Any]] = []
    first_ts = _number(logs[0].get("timestamp")) if logs else None
    if logs and initial_cash:
        curve.append({"timestamp": first_ts, "equity": initial_cash})
    for fill in logs:
        equity = _number(fill.get("equity_after"))
        if equity is not None:
            curve.append({"timestamp": _number(fill.get("timestamp")), "equity": equity})
    if final_equity is None and curve:
        final_equity = curve[-1]["equity"]

    peak = -math.inf
    max_drawdown_pct = 0.0
    max_drawdown_abs = 0.0
    drawdown_points: list[dict[str, Any]] = []
    for point in curve:
        peak = max(peak, point["equity"])
        drawdown_abs = point["equity"] - peak
        drawdown_pct = drawdown_abs / peak * 100 if peak > 0 else 0.0
        max_drawdown_pct = min(max_drawdown_pct, drawdown_pct)
        max_drawdown_abs = min(max_drawdown_abs, drawdown_abs)
        drawdown_points.append({"timestamp": point["timestamp"], "drawdown_pct": _round(drawdown_pct, 4)})

    trips = _round_trips(logs, initial_cash)
    pnls = [trip["pnl"] for trip in trips]
    returns = [trip["return_pct"] / 100 for trip in trips if trip["return_pct"] is not None]
    wins = [pnl for pnl in pnls if pnl > 0]
    losses = [pnl for pnl in pnls if pnl < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    durations = [trip["duration_seconds"] for trip in trips if trip["duration_seconds"] is not None]

    exposure_pct = None
    last_ts = _number(logs[-1].get("timestamp")) if logs else None
    if first_ts is not None and last_ts is not None and last_ts > first_ts:
        exposure_pct = min(sum(durations) / (last_ts - first_ts) * 100, 100.0)

    net_pnl = final_equity - initial_cash if final_equity is not None and initial_cash else None
    return_pct = net_pnl / initial_cash * 100 if net_pnl is not None and initial_cash else None
    avg_win = gross_profit / len(wins) if wins else None
    avg_loss = -gross_loss / len(losses) if losses else None
    win_streak, loss_streak = _streaks(pnls)

    by_side: dict[str, dict[str, Any]] = {}
    for trip in trips:
        bucket = by_side.setdefault(trip["side"], {"side": trip["side"], "trades": 0, "wins": 0, "net_pnl": 0.0})
        bucket["trades"] += 1
        bucket["wins"] += 1 if trip["pnl"] > 0 else 0
        bucket["net_pnl"] += trip["pnl"]
    for bucket in by_side.values():
        bucket["win_rate_pct"] = _round(bucket["wins"] / bucket["trades"] * 100, 2)
        bucket["net_pnl"] = _round(bucket["net_pnl"])

    summary = {
        "initial_cash": _round(initial_cash),
        "final_equity": _round(final_equity),
        "net_pnl": _round(net_pnl),
        "return_pct": _round(return_pct, 4),
        "fills": len(logs),
        "round_trips": len(trips),
        "open_position": bool(logs) and abs(_number(logs[-1].get("position_after")) or 0.0) > POSITION_EPSILON,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": _round(len(wins) / len(trips) * 100, 2) if trips else None,
        "profit_factor": _round(gross_profit / gross_loss, 4) if gross_loss > 0 else None,
        "gross_profit": _round(gross_profit),
        "gross_loss": _round(gross_loss),
        "avg_win": _round(avg_win),
        "avg_loss": _round(avg_loss),
        "payoff_ratio": _round(avg_win / -avg_loss, 4) if avg_win and avg_loss else None,
        "expectancy": _round(sum(pnls) / len(pnls)) if pnls else None,
        "best_trade": _round(max(pnls)) if pnls else None,
        "worst_trade": _round(min(pnls)) if pnls else None,
        "max_win_streak": win_streak,
        "max_loss_streak": loss_streak,
        "max_drawdown_pct": _round(max_drawdown_pct, 4) if curve else None,
        "max_drawdown_abs": _round(max_drawdown_abs) if curve else None,
        "recovery_factor": (
            _round(net_pnl / -max_drawdown_abs, 4) if net_pnl is not None and max_drawdown_abs < 0 else None
        ),
        "sharpe_per_trade": _round(_ratio(returns, downside_only=False), 4),
        "sortino_per_trade": _round(_ratio(returns, downside_only=True), 4),
        "avg_hold_seconds": _round(sum(durations) / len(durations), 1) if durations else None,
        "exposure_pct": _round(exposure_pct, 2),
        "total_fees": _round(_number(metrics.get("total_fees")) or _number(cash_flow.get("total_fees"))),
    }
    return {
        "summary": summary,
        "equity_curve": _downsample(curve),
        "drawdown_curve": _downsample(drawdown_points),
        "trade_pnls": [
            {
                "index": index + 1,
                "side": trip["side"],
                "entry_timestamp": trip["entry_timestamp"],
                "exit_timestamp": trip["exit_timestamp"],
                "pnl": _round(trip["pnl"]),
                "return_pct": _round(trip["return_pct"], 4),
                "duration_seconds": trip["duration_seconds"],
            }
            for index, trip in enumerate(trips)
        ][-MAX_CURVE_POINTS:],
        "by_side": list(by_side.values()),
    }
