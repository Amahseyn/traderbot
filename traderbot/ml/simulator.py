from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from traderbot.ml.simulation_config import SimulationConfig
from traderbot.ml.utils import (
    buy_hold_value,
    final_equity_from_curve,
    lookup_value_at_or_before,
    point_at_or_after,
)


@dataclass(frozen=True, slots=True)
class SimulationOutcome:
    metrics: dict[str, float]
    strategy_equity: list[float]
    buy_hold_equity: list[float]


def simulate_holdout_account(
    y_true: list[float],
    y_pred: list[float],
    timestamps: list[int],
    *,
    horizon_bars: int,
    bar_minutes: int,
    price_series: Sequence[tuple[int, float]],
    initial_usd = 100.0,
    sim_config: SimulationConfig | None = None,
    hold_bars: int | None = None,
    decision_bars: int | None = None,
) -> SimulationOutcome:
    """
    Walk-forward paper account on holdout forecasts.

    Labels are forward log returns over ``horizon_bars``. After entering long, the
    next decision waits ``hold_bars`` (default ``horizon_bars``). When flat, advance
    ``decision_bars`` (default 1 bar).

    Buy & hold: one position from the first holdout time through the end of the
    last forward window (close ratio on ``price_series``).
    """
    if len(y_true) != len(y_pred) or len(y_true) != len(timestamps):
        raise ValueError("y_true, y_pred, and timestamps must have the same length")
    if horizon_bars < 1:
        raise ValueError("horizon_bars must be >= 1")
    if bar_minutes < 1:
        raise ValueError("bar_minutes must be >= 1")
    cfg = sim_config or SimulationConfig(
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
        hold_bars=hold_bars,
        decision_bars=decision_bars if decision_bars is not None else 1,
    )
    hold_bars_res = cfg.resolved_hold_bars()
    decision_bars_res = cfg.resolved_decision_bars()

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
    hold_sec = hold_bars_res * bar_sec
    decision_sec = decision_bars_res * bar_sec

    t_start = points[0][0]
    t_last = points[-1][0]
    t_end = t_last + hold_sec

    c_start = lookup_value_at_or_before(price_series, t_start)
    c_end = lookup_value_at_or_before(price_series, t_end)
    buy_hold_final = buy_hold_value(initial_usd, c_start, c_end)

    equity = initial_usd
    strat_curve = [initial_usd]
    bh_curve = [initial_usd]
    next_decision_ts = t_start
    trades = 0
    wins = 0
    steps = 0

    while next_decision_ts <= t_last:
        row = point_at_or_after(points, next_decision_ts)
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
            next_decision_ts = ts + decision_sec
        strat_curve.append(equity)
        bh_curve.append(
            buy_hold_value(initial_usd, c_start, lookup_value_at_or_before(price_series, min(ts, t_end)))
        )

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