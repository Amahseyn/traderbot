from __future__ import annotations

import json
from pathlib import Path

from lab.store.database import open_database
from lab.store.hooks import record_model_forecast, record_strategy_backtest


def sync_results_tree(
    root: Path,
    *,
    database_path: Path | None = None,
) -> dict[str, int]:
    """Index existing ``results.json`` and ``backtest_summary.json`` files under ``root``."""
    counts = {"model": 0, "strategy": 0, "skipped": 0}
    connection = open_database(database_path)
    try:
        for results_path in root.rglob("results.json"):
            try:
                payload = json.loads(results_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                counts["skipped"] += 1
                continue
            if "model_id" not in payload:
                counts["skipped"] += 1
                continue
            record_model_forecast(
                result_dict=payload,
                out_dir=results_path.parent,
                csv_path=_guess_csv_from_run_dir(results_path.parent),
                database_path=database_path,
            )
            counts["model"] += 1

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


def _guess_csv_from_run_dir(run_dir: Path) -> Path | None:
    parts = run_dir.parts
    if "ohlc" in parts or "horizons" in parts:
        for parent in run_dir.parents:
            if parent.name in ("ohlc", "5m", "1h", "4h", "horizons"):
                candidate = parent / f"{run_dir.parent.name}.csv"
                if candidate.is_file():
                    return candidate
    return None
