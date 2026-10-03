from __future__ import annotations

import math

from traderbot.ml.simulation_config import SimulationConfig

DEFAULT_SAMPLE_USD = 100.0


def regression_metrics(y_true: list[float], y_pred: list[float]) -> dict[str, float]:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    if not y_true:
        return {"mae": 0.0, "rmse": 0.0, "directional_accuracy": 0.0, "n": 0.0}
    n = len(y_true)
    abs_err = 0.0
    sq_err = 0.0
    direction_hits = 0
    for t, p in zip(y_true, y_pred, strict=True):
        abs_err += abs(t - p)
        sq_err += (t - p) ** 2
        if (t >= 0 and p >= 0) or (t < 0 and p < 0):
            direction_hits += 1
    return {
        "mae": abs_err / n,
        "rmse": math.sqrt(sq_err / n),
        "directional_accuracy": direction_hits / n,
        "n": float(n),
    }


def full_metrics(
    y_true: list[float],
    y_pred: list[float],
    *,
    timestamps: list[int] | None = None,
    horizon_bars = 1,
    bar_minutes = 60,
    price_series: list[tuple[int, float]] | None = None,
    initial_usd: float = DEFAULT_SAMPLE_USD,
    simulation: object | None = None,
    sim_config: SimulationConfig | None = None,
) -> dict[str, float]:
    from traderbot.ml.simulator import simulate_holdout_account

    out = regression_metrics(y_true, y_pred)
    if simulation is not None:
        out.update(simulation.metrics)
        return out
    if timestamps is None or price_series is None:
        raise ValueError("timestamps and price_series required for account simulation")
    sim = simulate_holdout_account(
        y_true,
        y_pred,
        timestamps,
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
        price_series=price_series,
        initial_usd=initial_usd,
        sim_config=sim_config,
    )
    out.update(sim.metrics)
    return out


def format_metrics_block(metrics: dict[str, float]) -> str:
    n = int(metrics.get("n", 0))
    lines = [
        f"n = {n}",
        f"MAE = {metrics['mae']:.6f}",
        f"RMSE = {metrics['rmse']:.6f}",
        f"Dir. accuracy = {metrics['directional_accuracy']:.2%}",
    ]
    if "strategy_final_usd" in metrics:
        init = metrics.get("initial_usd", DEFAULT_SAMPLE_USD)
        lines.extend(
            [
                "",
                f"Sample ${init:.0f}",
                f"Strategy → ${metrics['strategy_final_usd']:.2f} ({metrics['strategy_return_pct']:+.2f}%)",
                f"Profit: ${metrics['strategy_profit_usd']:+.2f}",
                f"Buy & hold → ${metrics['buy_hold_final_usd']:.2f} ({metrics['buy_hold_return_pct']:+.2f}%)",
                f"Benefit vs B&H: ${metrics['excess_profit_usd']:+.2f}",
                f"Wins when long: {metrics['strategy_win_rate']:.1%} ({int(metrics['strategy_trades'])} trades, non-overlap)",
            ]
        )
    return "\n".join(lines)


def format_metrics_line(metrics: dict[str, float], *, prefix = "") -> str:
    base = (
        f"{prefix}MAE={metrics['mae']:.6f} "
        f"RMSE={metrics['rmse']:.6f} "
        f"dir_acc={metrics['directional_accuracy']:.2%} "
        f"n={int(metrics.get('n', 0))}"
    )
    if "strategy_final_usd" not in metrics:
        return base
    return (
        f"{base} | ${metrics['initial_usd']:.0f}→"
        f"${metrics['strategy_final_usd']:.2f} "
        f"({metrics['strategy_return_pct']:+.2f}%) "
        f"profit=${metrics['strategy_profit_usd']:+.2f} "
        f"vs_B&H=${metrics['excess_profit_usd']:+.2f}"
    )
