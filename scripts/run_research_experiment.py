#!/usr/bin/env python3
"""Master Research Mode Experiment Runner.

Orchestrates multi-asset (5 coins) x multi-timeframe (all 6 resolutions) x
multi-strategy (all 20 algorithms) evaluations with comparative optimizer benchmarks
(Grid vs Optuna TPE vs Optuna Random; Validation vs In-Sample).
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from traderbot.algorithms.registry import (
    algorithm_for_id,
    backtest_strategy_ids,
    pair_algorithm_for_id,
)
from traderbot.algorithms.strategy_exchanges import strategy_supported_on
from traderbot.algorithms.strategies.funding_carry import FundingCarryAlgorithm
from traderbot.analysis.optimizer_benchmark import (
    OptimizerShootoutConfig,
    run_optimizer_shootout,
)
from traderbot.backtesting.eval_data import fetch_history_bars
from traderbot.backtesting.funding_carry_engine import run_funding_carry_backtest
from traderbot.backtesting.matrix_eval import (
    EVAL_RESOLUTIONS,
    FUNDING_PARAM_GRID,
    GRID_PARAM_GRID,
    MAX_PARAM_COMBOS,
    MIN_TRADES_TRAIN,
    MIN_WINDOW_BARS,
    MM_PARAM_GRID,
    PAIR_PARAM_GRID,
    SAMPLE_WORKERS,
    _param_combos,
    _random_window,
    _split_train_test,
    _tune_funding,
    _tune_pair,
    _tune_single_asset,
    evaluate_funding_cell,
    evaluate_pair_cell,
    evaluate_single_asset_cell,
)
from traderbot.backtesting.oos_metrics import aggregate_sample_metrics
from traderbot.hyperliquid.funding import fetch_hyperliquid_funding_history
from traderbot.markets.execution_costs import execution_cost_profile

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("research_experiment")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Traderbot Comprehensive Research Mode Experiment")
    parser.add_argument(
        "--assets",
        type=str,
        default="btc,eth,sol,arb,doge",
        help="Comma-separated symbols (default: btc,eth,sol,arb,doge)",
    )
    parser.add_argument(
        "--timeframes",
        type=str,
        default="1,5,15,60,240,D",
        help="Comma-separated resolutions (default: 1,5,15,60,240,D)",
    )
    parser.add_argument(
        "--exchange",
        type=str,
        default="hyperliquid",
        help="Exchange venue (default: hyperliquid)",
    )
    parser.add_argument(
        "--history-months",
        type=int,
        default=6,
        help="Historical data range in months (default: 6)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=30,
        help="Monte Carlo OOS evaluation samples per matrix cell (default: 30)",
    )
    parser.add_argument(
        "--shootout-trials",
        type=int,
        default=25,
        help="Optuna trials for optimizer shootout (default: 25)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("results/research_experiment"),
        help="Directory to save experimental results",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Fast smoke test mode (2 assets, 2 timeframes, 3 strategies, 5 samples)",
    )
    parser.add_argument(
        "--skip-shootout",
        action="store_true",
        help="Skip optimizer shootout phase",
    )
    parser.add_argument(
        "--skip-matrix",
        action="store_true",
        help="Skip broad strategy matrix phase",
    )
    return parser.parse_args(argv)


def ingest_and_cache_market_data(
    assets: list[str],
    timeframes: list[str],
    exchange: str,
    months: int,
    log: Callable[[str], None],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Preflight and cache historical bar series for all assets and timeframes."""
    log(f"--- Phase 1: Market Data Ingestion ({exchange.upper()}) ---")
    data_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for asset in assets:
        for tf in timeframes:
            log(f"Loading {exchange} {asset.upper()} (resolution {tf})…")
            bars = fetch_history_bars(
                exchange=exchange,
                symbol_key=asset,
                resolution=tf,
                months=months,
                use_cache=True,
            )
            data_cache[(asset, tf)] = bars
            log(f"  -> {asset.upper()}:{tf} cached with {len(bars)} bars")
    return data_cache


def run_shootout_phase(
    assets: list[str],
    timeframes: list[str],
    exchange: str,
    trials: int,
    months: int,
    out_dir: Path,
    log: Callable[[str], None],
) -> dict[str, Any]:
    """Execute head-to-head optimizer shootout."""
    log("--- Phase 2: Optimizer Head-to-Head Shootout ---")
    shootout_assets = tuple(assets[:2])
    shootout_tfs = tuple(tf for tf in ("15", "60") if tf in timeframes) or tuple(timeframes[:2])
    shootout_strategies = ("bollinger_mean_reversion", "ema_cross", "breakout_atr")

    config = OptimizerShootoutConfig(
        assets=shootout_assets,
        timeframes=shootout_tfs,
        strategies=shootout_strategies,
        methods=("grid", "optuna_tpe", "optuna_random"),
        selection_modes=("validation", "in_sample"),
        optuna_trials=trials,
        exchange=exchange,
        history_months=months,
        out_dir=out_dir / "shootout",
    )
    shootout_results = run_optimizer_shootout(config, log=log)
    shootout_path = out_dir / "shootout_summary.json"
    shootout_path.write_text(json.dumps(shootout_results, indent=2), encoding="utf-8")
    log(f"Shootout results saved to {shootout_path}")
    return shootout_results


def run_strategy_matrix_phase(
    assets: list[str],
    timeframes: list[str],
    data_cache: dict[tuple[str, str], list[dict[str, Any]]],
    exchange: str,
    sample_count: int,
    out_dir: Path,
    smoke: bool,
    log: Callable[[str], None],
) -> dict[str, Any]:
    """Execute broad strategy matrix across assets, timeframes, and strategies."""
    log("--- Phase 3: Broad Strategy Matrix (Walk-Forward OOS) ---")
    all_strategies = backtest_strategy_ids()
    if smoke:
        strategies_to_eval = [s for s in ("bollinger_mean_reversion", "ema_cross", "rsi_threshold") if s in all_strategies]
    else:
        strategies_to_eval = all_strategies

    log(f"Evaluating {len(strategies_to_eval)} strategies across {len(assets)} assets and {len(timeframes)} timeframes…")

    rng = random.Random(42)
    from traderbot.backtesting.matrix_eval import MatrixEvalConfig

    config = MatrixEvalConfig(
        sample_count=sample_count,
        seed=42,
        out_dir=out_dir,
        use_cache=True,
    )

    all_results: dict[str, Any] = {
        "config": {
            "assets": assets,
            "timeframes": timeframes,
            "sample_count": sample_count,
            "exchange": exchange,
            "strategies": strategies_to_eval,
        },
        "cells": {},
    }

    # Evaluate single asset cells
    total_cells = len(assets) * len(timeframes) * len(strategies_to_eval)
    completed_cells = 0

    for asset in assets:
        for tf in timeframes:
            bars = data_cache.get((asset, tf), [])
            if len(bars) < MIN_WINDOW_BARS:
                log(f"Skipping {asset}:{tf}: only {len(bars)} bars (< {MIN_WINDOW_BARS})")
                completed_cells += len(strategies_to_eval)
                continue

            for strategy_id in strategies_to_eval:
                if not strategy_supported_on(strategy_id, exchange):
                    completed_cells += 1
                    continue

                cell_key = f"{exchange}:{asset}:{tf}:{strategy_id}"
                log(f"[{completed_cells + 1}/{total_cells}] Eval {cell_key}")

                samples = evaluate_single_asset_cell(
                    exchange=exchange,
                    strategy_id=strategy_id,
                    symbol_key=asset,
                    resolution=tf,
                    bars=bars,
                    config=config,
                    rng=rng,
                )

                aggregate = aggregate_sample_metrics(samples)
                aggregate["median_excess_vs_buy_hold_pct"] = round(
                    statistics.median([s.get("excess_vs_buy_hold_pct", 0.0) for s in samples])
                    if samples
                    else 0.0,
                    4,
                )
                all_results["cells"][cell_key] = {
                    "asset": asset,
                    "resolution": tf,
                    "strategy_id": strategy_id,
                    "samples": len(samples),
                    "aggregate": aggregate,
                }
                completed_cells += 1

                # Incremental write
                (out_dir / "matrix_summary.json").write_text(
                    json.dumps(all_results, indent=2),
                    encoding="utf-8",
                )

    matrix_path = out_dir / "matrix_summary.json"
    matrix_path.write_text(json.dumps(all_results, indent=2), encoding="utf-8")
    log(f"Matrix evaluation complete. Saved to {matrix_path}")
    return all_results


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    assets = [s.strip().lower() for s in args.assets.split(",") if s.strip()]
    timeframes = [tf.strip() for tf in args.timeframes.split(",") if tf.strip()]

    if args.smoke:
        assets = assets[:2]
        timeframes = [tf for tf in ("15", "60") if tf in timeframes] or timeframes[:2]
        sample_count = min(args.samples, 5)
        shootout_trials = min(args.shootout_trials, 6)
    else:
        sample_count = args.samples
        shootout_trials = args.shootout_trials

    def log(msg: str) -> None:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

    log(f"Starting Comprehensive Research Experiment on {args.exchange.upper()}")
    log(f"Assets: {assets}")
    log(f"Timeframes: {timeframes}")

    # Phase 1: Ingestion
    data_cache = ingest_and_cache_market_data(
        assets=assets,
        timeframes=timeframes,
        exchange=args.exchange,
        months=args.history_months,
        log=log,
    )

    # Phase 2: Optimizer Shootout
    shootout_results = {}
    if not args.skip_shootout:
        shootout_results = run_shootout_phase(
            assets=assets,
            timeframes=timeframes,
            exchange=args.exchange,
            trials=shootout_trials,
            months=args.history_months,
            out_dir=out_dir,
            log=log,
        )

    # Phase 3: Strategy Matrix
    matrix_results = {}
    if not args.skip_matrix:
        matrix_results = run_strategy_matrix_phase(
            assets=assets,
            timeframes=timeframes,
            data_cache=data_cache,
            exchange=args.exchange,
            sample_count=sample_count,
            out_dir=out_dir,
            smoke=args.smoke,
            log=log,
        )

    # Phase 4: Synthesis & Executive Report
    log("--- Phase 4: Synthesizing Findings & Generating Report ---")
    from scripts.build_comprehensive_research_report import build_report

    report_path = REPO_ROOT / "docs" / "superpowers" / "reports" / "comprehensive_research_experiment_report.md"
    selector_path = REPO_ROOT / "config" / "strategy_selector.json"

    build_report(
        shootout_path=out_dir / "shootout_summary.json" if not args.skip_shootout else None,
        matrix_path=out_dir / "matrix_summary.json" if not args.skip_matrix else None,
        report_path=report_path,
        selector_path=selector_path,
        log=log,
    )

    log(f"Experiment Complete! Report generated at {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
