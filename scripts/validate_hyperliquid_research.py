#!/usr/bin/env python3
"""
Hyperliquid research pipeline check: export N bars, optimize all strategies per interval,
then compare with sweep winners. Emits structured logs for CI or manual runs.

Example:
  python scripts/validate_hyperliquid_research.py --src arb --intervals 1,5 --max-bars 100
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from traderbot.algorithms.registry import backtest_strategy_ids
from traderbot.backtesting.research_windows import MIN_OPTIMIZER_TRAIN_BARS, MIN_COMPARE_EVAL_BARS
from traderbot.backtesting import load_bars_csv
from traderbot.data.export import run_export
from traderbot.markets.market_data import market_symbol
from traderbot.utils.resolution import resolution_from_csv_path, resolution_minutes

LOG = logging.getLogger("hyperliquid.research.validate")


def _configure_logging(log_file: Path | None, verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s — %(message)s")
        )
        logging.getLogger().addHandler(handler)
        LOG.info("writing log file %s", log_file)


def _run_start_unix_for_walk_forward(csv_path: Path, train_fraction: float = 0.65) -> int:
    bars = load_bars_csv(csv_path)
    if len(bars) < MIN_OPTIMIZER_TRAIN_BARS + MIN_COMPARE_EVAL_BARS:
        raise ValueError(
            f"{csv_path.name}: need at least {MIN_OPTIMIZER_TRAIN_BARS + MIN_COMPARE_EVAL_BARS} bars, got {len(bars)}"
        )
    split_index = int(len(bars) * train_fraction)
    split_index = max(MIN_OPTIMIZER_TRAIN_BARS, split_index)
    split_index = min(split_index, len(bars) - MIN_COMPARE_EVAL_BARS)
    run_start = int(bars[split_index]["timestamp"])
    resolution = resolution_from_csv_path(csv_path.name)
    bar_minutes = resolution_minutes(resolution) or 60
    train_count = split_index
    eval_count = len(bars) - split_index
    LOG.info(
        "%s walk-forward: run_start_unix=%s train_bars≈%s eval_bars≈%s (resolution=%s, %sm)",
        csv_path.name,
        run_start,
        train_count,
        eval_count,
        resolution,
        bar_minutes,
    )
    return run_start


def run_validation(
    *,
    src: str,
    dst: str,
    intervals: list[str],
    max_bars: int,
    output_dir: Path,
    database_path: Path | None,
    train_fraction: float,
) -> dict:
    from lab.custom_research import run_custom_research

    if database_path is not None:
        os.environ["TRADERBOT_DB"] = str(database_path)
        LOG.info("TRADERBOT_DB=%s", database_path)

    symbol = market_symbol(src, dst)
    export_days = max(2, (max_bars * 5) // 1440 + 1)
    jobs = [
        {
            "symbol": symbol,
            "src": src.strip().lower(),
            "dst": dst.strip().lower(),
            "interval": interval,
            "days": export_days,
            "max_bars": max_bars,
            "exchange": "hyperliquid",
        }
        for interval in intervals
    ]
    LOG.info(
        "export hyperliquid %s intervals=%s max_bars=%s days=%s",
        symbol,
        intervals,
        max_bars,
        export_days,
    )
    t0 = time.perf_counter()
    written = run_export(jobs, days=export_days, output_dir=output_dir, to_ts=None, crypto_layout=False)
    LOG.info("export done in %.1fs: %s", time.perf_counter() - t0, [str(p) for p in written])

    if not written:
        raise RuntimeError("export produced no CSV files")

    strategy_ids = backtest_strategy_ids()
    LOG.info("strategies to optimize/compare: %s (%d)", strategy_ids, len(strategy_ids))

    # Same run_start for all files in this batch (per-file split is more accurate)
    run_starts = {str(path): _run_start_unix_for_walk_forward(path, train_fraction) for path in written}

    summaries: list[dict] = []
    for csv_path in written:
        body = {
            "compare_strategies": True,
            "optimize_before_compare": True,
            "strategy_ids": strategy_ids,
            "visualize": False,
            "cash": 10_000.0,
            "fee": 0.00045,
            "execution": "next_open",
            "optimize_holdout_tail_bars": max(5, max_bars // 10),
            "optimize_min_trades": 0,
            "optimize_max_combos": 64,
            "run_start_unix_seconds": run_starts[str(csv_path)],
            "dataset_rows": [{"repo_path": str(csv_path.resolve())}],
        }
        LOG.info("=== custom_research %s ===", csv_path.name)

        def _log(msg: str, *_args, **_kwargs) -> None:
            LOG.info("%s", msg)

        summary = run_custom_research(body, log=_log)
        summaries.append(summary)

    report = {
        "symbol": symbol,
        "exchange": "hyperliquid",
        "intervals": intervals,
        "max_bars": max_bars,
        "strategy_count": len(strategy_ids),
        "csv_files": [str(p) for p in written],
        "run_start_unix_by_csv": run_starts,
        "summaries": summaries,
    }
    return report


def _assert_report_ok(report: dict) -> None:
    strategy_count = int(report["strategy_count"])
    for summary in report["summaries"]:
        optimize_step = next((s for s in summary.get("steps", []) if s.get("step") == "optimize"), None)
        if optimize_step is None:
            raise AssertionError(f"missing optimize step in {summary}")
        if optimize_step.get("sweeps", 0) < strategy_count:
            raise AssertionError(
                f"expected at least {strategy_count} sweeps per file, got {optimize_step}"
            )
        compare_step = next((s for s in summary.get("steps", []) if s.get("step") == "compare"), None)
        if compare_step is None or compare_step.get("datasets", 0) < 1:
            raise AssertionError(f"compare failed: {compare_step}")
        optimize_rows = summary.get("optimize") or []
        failed = [r for r in optimize_rows if r.get("skipped")]
        if failed:
            raise AssertionError(f"sweep failures: {failed[:3]} ... ({len(failed)} total)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", default="arb", help="Hyperliquid coin (default: arb)")
    parser.add_argument("--dst", default="usdt", help="Quote (default: usdt)")
    parser.add_argument("--intervals", default="1,5", help="Comma-separated resolutions")
    parser.add_argument("--max-bars", type=int, default=100, help="Closed candles per interval")
    parser.add_argument("--out", type=Path, default=Path("data/validate_hyperliquid"))
    parser.add_argument("--db", type=Path, default=None, help="SQLite path for sweep_sessions")
    parser.add_argument("--log-file", type=Path, default=None)
    parser.add_argument("--train-fraction", type=float, default=0.65)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json-report", type=Path, default=None)
    args = parser.parse_args(argv)

    _configure_logging(args.log_file, args.verbose)
    intervals = [part.strip() for part in str(args.intervals).split(",") if part.strip()]
    if not intervals:
        parser.error("at least one interval required")

    report = run_validation(
        src=args.src,
        dst=args.dst,
        intervals=intervals,
        max_bars=args.max_bars,
        output_dir=args.out,
        database_path=args.db,
        train_fraction=args.train_fraction,
    )
    _assert_report_ok(report)
    LOG.info("VALIDATION OK — hyperliquid %s × %s strategies × intervals %s", report["symbol"], report["strategy_count"], intervals)
    if args.json_report:
        args.json_report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        LOG.info("wrote %s", args.json_report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
