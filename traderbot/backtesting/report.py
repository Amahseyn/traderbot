from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from traderbot.algorithms.base import Algorithm
from traderbot.algorithms.visualize import (
    render_backtest_plots,
    visualization_paths_to_dict,
)
from traderbot.backtesting.engine import BacktestResult


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
    }
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
