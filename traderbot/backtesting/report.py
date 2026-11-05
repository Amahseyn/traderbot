from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from traderbot.algorithms.base import Algorithm
from traderbot.backtesting.engine import (
    BacktestResult,
    build_cash_flow_summary,
    build_trade_log_entries,
)
from traderbot.backtesting.trade_stats import trade_stats


def backtest_summary_dict(
    algorithm: Algorithm,
    result: BacktestResult,
    *,
    bars: int,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "algorithm": algorithm.name,
        "bars": bars,
        "trades": len(result.trades),
        "initial_cash": result.initial_cash,
        "final_equity": round(result.final_equity, 6),
        "return_pct": round(result.return_pct, 6),
        "fee_rate": result.fee_rate,
        "slippage_rate": result.slippage_rate,
        "execution": result.execution,
        "total_fees": round(result.total_fees, 6),
        **trade_stats(result),
        "cash_flow": build_cash_flow_summary(result),
        "trade_logs": build_trade_log_entries(result),
    }
    if extra:
        payload.update(extra)
    return payload


def pair_backtest_summary_dict(
    result: Any,
    *,
    bars: int,
    benchmarks: dict[str, float] | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from traderbot.backtesting.metrics import (
        annualized_sharpe_ratio,
        annualized_sortino_ratio,
        calmar_ratio,
        calculate_returns_from_equity_curve,
        exposure_time_pct,
        turnover_ratio,
    )

    returns = calculate_returns_from_equity_curve(result.equity_curve)
    sharpe = annualized_sharpe_ratio(returns)
    sortino = annualized_sortino_ratio(returns)
    calmar = calmar_ratio(result.return_pct, result.max_drawdown_pct)
    exp_time = exposure_time_pct(result.exposure_curve) if hasattr(result, "exposure_curve") else 0.0
    turnover = turnover_ratio(result.trades, result.initial_cash)

    payload: dict[str, Any] = {
        "bars": bars,
        "trades": len(result.trades),
        "initial_cash": result.initial_cash,
        "final_equity": round(result.final_equity, 6),
        "marked_equity": round(getattr(result, "marked_equity", result.final_equity), 6),
        "liquidated_equity": round(getattr(result, "liquidated_equity", result.final_equity), 6),
        "return_pct": round(result.return_pct, 6),
        "max_drawdown_pct": round(result.max_drawdown_pct, 6),
        "annualized_sharpe": round(sharpe, 4) if sharpe is not None else None,
        "annualized_sortino": round(sortino, 4) if sortino is not None else None,
        "calmar_ratio": round(calmar, 4) if calmar is not None else None,
        "win_rate_pct": getattr(result, "win_rate_pct", None),
        "turnover_ratio": round(turnover, 4),
        "exposure_time_pct": round(exp_time, 2),
        "fee_rate": getattr(result, "fee_rate", 0.0),
        "total_fees": round(getattr(result, "total_fees", 0.0), 6),
        "total_funding": round(getattr(result, "total_funding", 0.0), 6),
        "total_funding_paid": round(getattr(result, "total_funding_paid", 0.0), 6),
        "total_funding_received": round(getattr(result, "total_funding_received", 0.0), 6),
        "total_slippage_cost": round(getattr(result, "total_slippage_cost", 0.0), 6),
        "execution": getattr(result, "execution", "next_open"),
    }
    if benchmarks:
        payload["benchmarks"] = benchmarks
    if hasattr(result, "breakdown_events") and result.breakdown_events:
        payload["breakdown_events"] = result.breakdown_events
    if extra:
        payload.update(extra)
    return payload



def save_backtest_result(
    algorithm: Algorithm,
    result: BacktestResult,
    out_dir: Path,
    *,
    bars: int,
    bar_rows: list[dict[str, Any]] | None = None,
    visualize = False,
    write_plot = False,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Write ``backtest_summary.json`` and optional charts under ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    viz_payload: dict[str, Any] | None = None
    if visualize and result.equity_curve and bar_rows is not None:
        try:
            from traderbot.algorithms.visualize import (
                render_backtest_plots,
                visualization_paths_to_dict,
            )

            paths = render_backtest_plots(algorithm, result, bar_rows, out_dir)
            viz_payload = visualization_paths_to_dict(paths)
        except ImportError:
            visualize = False
    summary_extra = dict(extra or {})
    if viz_payload is not None:
        summary_extra["visualization"] = viz_payload
    summary_path = out_dir / "backtest_summary.json"
    summary_path.write_text(
        json.dumps(
            backtest_summary_dict(algorithm, result, bars=bars, extra=summary_extra),
            indent=2,
        ),
        encoding="utf-8",
    )
    if write_plot and not visualize and result.equity_curve:
        _write_legacy_equity_plot(result, out_dir / "equity_curve.png")
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    from traderbot.recording import try_record

    try_record(
        "strategy_backtest",
        algorithm=algorithm,
        backtest_result=result,
        out_dir=out_dir,
        bars=bars,
        summary=summary_payload,
        extra=summary_extra,
        compare_session_id=summary_extra.get("compare_session_id"),
        experiment_id=summary_extra.get("experiment_id"),
    )
    return summary_path


def _write_legacy_equity_plot(result: BacktestResult, path: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    xs = [ts for ts, _ in result.equity_curve]
    ys = [eq for _, eq in result.equity_curve]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(xs, ys, color="#2563eb", linewidth=1.2, label="Strategy equity")
    ax.axhline(result.initial_cash, color="#94a3b8", linestyle="--", linewidth=0.8, label="Initial cash")
    ax.set_title("Backtest equity curve")
    ax.set_xlabel("Timestamp")
    ax.set_ylabel("Equity")
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
