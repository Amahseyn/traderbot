from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimulationOutcome:
    metrics: dict[str, float]
    strategy_equity: list[float]
    buy_hold_equity: list[float]


def _lookup_close(price_series: Sequence[tuple[int, float]], ts: int) -> float | None:
    close: float | None = None
    for bar_ts, bar_close in price_series:
        if bar_ts > ts:
            break
        close = bar_close
    return close


def _point_at_or_after(
    points: list[tuple[int, float, float]],
    ts: int,
) -> tuple[int, float, float] | None:
    for row in points:
        if row[0] >= ts:
            return row
    return None


def _buy_hold_mark(initial_usd: float, c_start: float | None, c_now: float | None) -> float:
    if c_start is None or c_now is None or c_start <= 0:
        return initial_usd
    return initial_usd * (c_now / c_start)


def simulate_holdout_account(
    y_true: list[float],
    y_pred: list[float],
    timestamps: list[int],
    *,
    horizon_bars: int,
    bar_minutes: int,
    price_series: Sequence[tuple[int, float]],
    initial_usd: float = 100.0,
) -> SimulationOutcome:
    """
    Walk-forward paper account on holdout forecasts.

    Labels are forward log returns over ``horizon_bars``. After entering long, the
    next decision waits ``horizon_bars`` so windows do not overlap. If flat and
    not long, advance one bar.

    Buy & hold: one position from the first holdout time through the end of the
    last forward window (close ratio on ``price_series``).
    """
    if len(y_true) != len(y_pred) or len(y_true) != len(timestamps):
        raise ValueError("y_true, y_pred, and timestamps must have the same length")
    if horizon_bars < 1:
        raise ValueError("horizon_bars must be >= 1")
    if bar_minutes < 1:
        raise ValueError("bar_minutes must be >= 1")

    empty_metrics = {
        "initial_usd": initial_usd,
        "strategy_final_usd": initial_usd,
        "buy_hold_final_usd": initial_usd,
        "strategy_profit_usd": 0.0,
        "buy_hold_profit_usd": 0.0,
        "excess_profit_usd": 0.0,
        "strategy_return_pct": 0.0,
        "buy_hold_return_pct": 0.0,
        "strategy_win_rate": 0.0,
        "strategy_trades": 0.0,
        "simulation_steps": 0.0,
    }
    if not y_true:
        return SimulationOutcome(
            metrics=empty_metrics,
            strategy_equity=[initial_usd],
            buy_hold_equity=[initial_usd],
        )

    points = sorted(zip(timestamps, y_true, y_pred, strict=True), key=lambda row: row[0])
    bar_sec = bar_minutes * 60
    hold_sec = horizon_bars * bar_sec

    t_start = points[0][0]
    t_last = points[-1][0]
    t_end = t_last + hold_sec

    c_start = _lookup_close(price_series, t_start)
    c_end = _lookup_close(price_series, t_end)
    buy_hold_final = _buy_hold_mark(initial_usd, c_start, c_end)

    equity = initial_usd
    strat_curve = [initial_usd]
    bh_curve = [initial_usd]
    next_decision_ts = t_start
    trades = 0
    wins = 0
    steps = 0

    while next_decision_ts <= t_last:
        row = _point_at_or_after(points, next_decision_ts)
        if row is None:
            break
        ts, actual, pred = row
        steps += 1
        if pred > 0:
            equity *= math.exp(actual)
            trades += 1
            if actual > 0:
                wins += 1
            next_decision_ts = ts + hold_sec
        else:
            next_decision_ts = ts + bar_sec
        strat_curve.append(equity)
        bh_curve.append(_buy_hold_mark(initial_usd, c_start, _lookup_close(price_series, min(ts, t_end))))

    strategy_final = equity
    strategy_profit = strategy_final - initial_usd
    buy_hold_profit = buy_hold_final - initial_usd

    metrics = {
        "initial_usd": initial_usd,
        "strategy_final_usd": strategy_final,
        "buy_hold_final_usd": buy_hold_final,
        "strategy_profit_usd": strategy_profit,
        "buy_hold_profit_usd": buy_hold_profit,
        "excess_profit_usd": strategy_profit - buy_hold_profit,
        "strategy_return_pct": (strategy_final / initial_usd - 1.0) * 100.0,
        "buy_hold_return_pct": (buy_hold_final / initial_usd - 1.0) * 100.0,
        "strategy_win_rate": (wins / trades) if trades else 0.0,
        "strategy_trades": float(trades),
        "simulation_steps": float(steps),
    }
    return SimulationOutcome(
        metrics=metrics,
        strategy_equity=strat_curve,
        buy_hold_equity=bh_curve,
    )


def final_equity_from_curve(curve: list[float]) -> float:
    return curve[-1] if curve else 100.0
