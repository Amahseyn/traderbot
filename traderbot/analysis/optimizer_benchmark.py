from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

from traderbot.algorithms.cli_args import default_strategy_namespace, merge_strategy_namespace
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.backtesting import run_backtest
from traderbot.backtesting.eval_data import fetch_history_bars
from traderbot.backtesting.oos_metrics import summarize_single_asset_run
from traderbot.backtesting.optimize_select import OptimizeSelectConfig, run_strategy_optimize
from traderbot.backtesting.robust_defaults import FULL_TUNE_GRIDS
from traderbot.backtesting.sweep import SweepOptions
from traderbot.markets.execution_costs import execution_cost_profile

logger = logging.getLogger(__name__)

BenchmarkMethod = Literal["grid", "optuna_tpe", "optuna_random"]
BenchmarkSelectionMode = Literal["validation", "in_sample"]


@dataclass(frozen=True, slots=True)
class OptimizerShootoutConfig:
    assets: tuple[str, ...] = ("btc", "sol")
    timeframes: tuple[str, ...] = ("15", "60")
    strategies: tuple[str, ...] = ("bollinger_mean_reversion", "ema_cross", "breakout_atr")
    methods: tuple[BenchmarkMethod, ...] = ("grid", "optuna_tpe", "optuna_random")
    selection_modes: tuple[BenchmarkSelectionMode, ...] = ("validation", "in_sample")
    optuna_trials: int = 40
    exchange: str = "hyperliquid"
    cash: float = 10_000.0
    history_months: int = 6
    out_dir: Path = Path("results/optimizer_shootout")


def compute_overfitting_index(train_return_pct: float, test_return_pct: float) -> float:
    """Overfitting index: normalized drop from train to test.

    Higher values (> 0.5) denote substantial curve fitting; values near or below 0
    denote robust out-of-sample persistence.
    """
    scale = max(abs(train_return_pct), 1.0)
    return round((train_return_pct - test_return_pct) / scale, 4)


def run_single_shootout_cell(
    *,
    strategy_id: str,
    bars: list[dict[str, Any]],
    method: BenchmarkMethod,
    selection_mode: BenchmarkSelectionMode,
    exchange: str = "hyperliquid",
    optuna_trials: int = 40,
    cash: float = 10_000.0,
    resolution: str = "60",
) -> dict[str, Any]:
    """Execute optimization under given method and selection mode and evaluate on holdout test bars."""
    if len(bars) < 60:
        raise ValueError(f"Need at least 60 bars for benchmark cell (got {len(bars)})")

    costs = execution_cost_profile(exchange, fee_role="taker")
    fee_rate = costs.fee_rate
    slippage_rate = costs.slippage_rate

    # Configure optimizer method
    if method == "grid":
        optimizer_method = "grid"
        sampler = "tpe"
    elif method == "optuna_tpe":
        optimizer_method = "optuna"
        sampler = "tpe"
    elif method == "optuna_random":
        optimizer_method = "optuna"
        sampler = "random"
    else:
        raise ValueError(f"Unknown benchmark method: {method}")

    param_grid = FULL_TUNE_GRIDS.get(strategy_id, {})
    options = SweepOptions(
        strategy_id=strategy_id,
        param_grid=param_grid,
        bars=bars,
        cash=cash,
        fee=fee_rate,
        slippage=slippage_rate,
        exchange=exchange,
        execution="close",
        min_trades=2,
    )

    opt_config = OptimizeSelectConfig(
        selection_mode=selection_mode,
        train_fraction=0.6,
        validation_fraction=0.2,
        holdout_fraction=0.2,
        optimizer_method=optimizer_method,
        optuna_sampler=sampler,
        n_trials=optuna_trials,
        full_grid_hints=True,
    )

    start_wall = time.perf_counter()
    namespace = default_strategy_namespace()
    result = run_strategy_optimize(options, namespace, config=opt_config)
    elapsed_seconds = round(time.perf_counter() - start_wall, 3)

    best_params = dict(result.get("best_params") or {})
    best_candidate = dict(result.get("best") or {})

    train_return_pct = float(best_candidate.get("return_pct") or 0.0)
    train_trades = int(best_candidate.get("trades") or 0)
    train_sharpe = float(best_candidate.get("sharpe_ratio") or 0.0)

    val_return_pct = best_candidate.get("validation_return_pct")
    if val_return_pct is not None:
        val_return_pct = float(val_return_pct)

    # Evaluate on the holdout test slice
    test_slice_len = max(1, int(len(bars) * 0.2))
    test_bars = bars[-test_slice_len:]

    # Instantiate algorithm with winning parameters
    merged_namespace = merge_strategy_namespace(namespace)
    for key, val in best_params.items():
        if hasattr(merged_namespace, key):
            setattr(merged_namespace, key, val)

    kwargs = strategy_kwargs_from_namespace(strategy_id, merged_namespace)
    algo = algorithm_for_id(strategy_id, **kwargs)
    test_backtest = run_backtest(
        algo,
        test_bars,
        initial_cash=cash,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
    )

    summary = summarize_single_asset_run(
        test_backtest,
        test_bars,
        resolution=resolution,
        algorithm=algo,
    )

    overfitting = compute_overfitting_index(train_return_pct, summary["return_pct"])

    return {
        "strategy_id": strategy_id,
        "method": method,
        "selection_mode": selection_mode,
        "resolution": resolution,
        "elapsed_seconds": elapsed_seconds,
        "best_params": best_params,
        "train_return_pct": round(train_return_pct, 4),
        "train_sharpe": round(train_sharpe, 4),
        "train_trades": train_trades,
        "val_return_pct": round(val_return_pct, 4) if val_return_pct is not None else None,
        "test_return_pct": summary["return_pct"],
        "test_sharpe_ratio": summary.get("sharpe_ratio", 0.0),
        "test_max_drawdown_pct": summary.get("max_drawdown_pct", 0.0),
        "test_trade_count": summary.get("trade_count", 0),
        "test_win_rate_pct": summary.get("win_rate_pct", 0.0),
        "buy_and_hold_return_pct": summary.get("buy_and_hold_return_pct", 0.0),
        "excess_vs_bnh_pct": summary.get("excess_vs_buy_hold_pct", 0.0),
        "overfitting_index": overfitting,
    }


def run_optimizer_shootout(
    config: OptimizerShootoutConfig,
    *,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run full factorial shootout across configured assets, timeframes, strategies, and methods."""
    printer = log or (lambda msg: None)
    config.out_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []

    for asset in config.assets:
        for tf in config.timeframes:
            printer(f"Shootout: Fetching {config.exchange} {asset} {tf}…")
            bars = fetch_history_bars(
                exchange=config.exchange,
                symbol_key=asset,
                resolution=tf,
                months=config.history_months,
                use_cache=True,
            )
            if len(bars) < 60:
                printer(f"Shootout: Skipping {asset} {tf}: insufficient bars ({len(bars)})")
                continue

            for strategy_id in config.strategies:
                for method in config.methods:
                    for mode in config.selection_modes:
                        cell_desc = f"{asset}:{tf}:{strategy_id} | {method} | {mode}"
                        printer(f"Shootout running {cell_desc}")
                        try:
                            cell_res = run_single_shootout_cell(
                                strategy_id=strategy_id,
                                bars=bars,
                                method=method,
                                selection_mode=mode,
                                exchange=config.exchange,
                                optuna_trials=config.optuna_trials,
                                cash=config.cash,
                                resolution=tf,
                            )
                            cell_res["asset"] = asset
                            results.append(cell_res)
                        except Exception as exc:
                            logger.exception("Shootout cell failed: %s: %s", cell_desc, exc)
                            printer(f"Shootout failed: {cell_desc}: {exc}")

    return {
        "config": {
            "assets": list(config.assets),
            "timeframes": list(config.timeframes),
            "strategies": list(config.strategies),
            "methods": list(config.methods),
            "selection_modes": list(config.selection_modes),
            "optuna_trials": config.optuna_trials,
            "exchange": config.exchange,
        },
        "cells": results,
    }
