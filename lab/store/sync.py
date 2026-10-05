from __future__ import annotations

import json
from pathlib import Path

from lab.store.database import open_database
from lab.store.hooks import record_strategy_backtest


def sync_results_tree(
    root: Path,
    *,
    database_path: Path | None = None,
) -> dict[str, int]:
    """Index existing ``backtest_summary.json`` files under ``root``."""
    counts = {"strategy": 0, "skipped": 0}
    connection = open_database(database_path)
    try:
        for summary_path in root.rglob("backtest_summary.json"):
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                counts["skipped"] += 1
                continue
            strategy_id = summary.get("strategy_id") or summary.get("algorithm")
            if not strategy_id:
                counts["skipped"] += 1
                continue
            from traderbot.algorithms.registry import algorithm_for_id

            try:
                algorithm = algorithm_for_id(strategy_id)
            except Exception:
                counts["skipped"] += 1
                continue
            from traderbot.backtesting.engine import BacktestResult

            backtest_result = BacktestResult(
                initial_cash=float(summary.get("initial_cash", 10_000)),
                final_equity=float(summary.get("final_equity", 10_000)),
                trades=[],
                equity_curve=[],
            )
            record_strategy_backtest(
                algorithm,
                backtest_result,
                out_dir=summary_path.parent,
                bars=int(summary.get("bars", 0)),
                summary=summary,
                extra={"strategy_id": strategy_id, "csv": summary.get("csv")},
                database_path=database_path,
            )
            counts["strategy"] += 1
    finally:
        connection.close()
    return counts
