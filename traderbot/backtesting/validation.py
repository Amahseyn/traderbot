from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traderbot.algorithms.cli_args import merge_strategy_namespace
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.backtesting import backtest_summary_dict, load_bars_csv, run_backtest
from traderbot.backtesting.metrics import buy_and_hold_return_pct, max_drawdown_pct, split_chronological
from traderbot.algorithms.registry import backtest_strategy_ids
from traderbot.backtesting.robust_defaults import tune_grid_for_strategy
from traderbot.backtesting.sweep import MAX_SWEEP_PARAMS
from traderbot.data.intrahour import enrich_bars_for_csv
from traderbot.utils.trading_costs import (
    ResolvesCostRates,
    DEFAULT_BACKTEST_EXECUTION,
)


@dataclass
class ValidationOptions(ResolvesCostRates):
    strategy_id: str
    param_grid: dict[str, list[Any]]
    csv_path: str | Path | None = None
    bars: list[dict[str, Any]] | None = None
    cash: float = 10_000.0
    fee: float | None = None
    slippage: float | None = None
    exchange: str | None = None
    execution: str = DEFAULT_BACKTEST_EXECUTION
    train_fraction: float = 0.6
    validation_fraction: float = 0.2
    min_trades: int = 1
    max_combos: int = 64


def run_strategy_validation(
    options: ValidationOptions,
    base_namespace: Any | None = None,
) -> dict[str, Any]:
    """
    Tune on train, select the best validation return, report test once (no test peeking).
    """
    if not options.param_grid or len(options.param_grid) > MAX_SWEEP_PARAMS:
        raise ValueError(f"validation requires 1-{MAX_SWEEP_PARAMS} params")
    combos = list(itertools.product(*options.param_grid.values()))
    if not combos:
        raise ValueError("validation param grid is empty")
    if len(combos) > options.max_combos:
        raise ValueError(f"validation has {len(combos)} combos; max is {options.max_combos}")

    base = merge_strategy_namespace(base_namespace)
    if options.bars is not None:
        bars = list(options.bars)
        csv_label = options.csv_path or options.strategy_id
    else:
        if not options.csv_path:
            raise ValueError("validation requires csv_path or preloaded bars")
        csv_label = str(options.csv_path)
        csv_file = Path(options.csv_path)
        bars = enrich_bars_for_csv(load_bars_csv(csv_file), csv_file, base)
        if not bars:
            raise ValueError(f"No bars in CSV: {options.csv_path}")

    train_bars, validation_bars, test_bars = split_chronological(
        bars,
        train_fraction=options.train_fraction,
        validation_fraction=options.validation_fraction,
    )
    names = list(options.param_grid.keys())
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for combo in combos:
        namespace = merge_strategy_namespace(base)
        params = dict(zip(names, combo))
        for key, value in params.items():
            setattr(namespace, key, value)
        try:
            train_algo = algorithm_for_id(
                options.strategy_id,
                **strategy_kwargs_from_namespace(options.strategy_id, namespace),
            )
            train_result = run_backtest(
                train_algo,
                train_bars,
                initial_cash=options.cash,
                fee_rate=options.fee,
                slippage_rate=options.slippage,
                execution=options.execution,
            )
            validation_algo = algorithm_for_id(
                options.strategy_id,
                **strategy_kwargs_from_namespace(options.strategy_id, namespace),
            )
            validation_result = run_backtest(
                validation_algo,
                validation_bars,
                initial_cash=options.cash,
                fee_rate=options.fee,
                slippage_rate=options.slippage,
                execution=options.execution,
            )
        except ValueError as exc:
            skipped.append({"params": params, "error": str(exc)})
            continue
        row = {
            "params": params,
            "train": backtest_summary_dict(
                train_algo,
                train_result,
                bars=len(train_bars),
                extra={"strategy_id": options.strategy_id},
            ),
            "validation": backtest_summary_dict(
                validation_algo,
                validation_result,
                bars=len(validation_bars),
                extra={"strategy_id": options.strategy_id},
            ),
            "eligible": (
                len(train_result.trades) >= options.min_trades
                and len(validation_result.trades) >= options.min_trades
            ),
        }
        candidates.append(row)

    if not candidates:
        reason = skipped[0]["error"] if skipped else "no combinations"
        raise ValueError(f"validation found no valid combos: {reason}")

    def _selection_key(row: dict[str, Any]) -> tuple[int, float, float]:
        validation_return = float(row["validation"]["return_pct"])
        train_return = float(row["train"]["return_pct"])
        return (
            1 if row["eligible"] else 0,
            validation_return,
            train_return,
        )

    candidates.sort(key=_selection_key, reverse=True)
    winner = candidates[0]
    winner_params = winner["params"]
    winner_namespace = merge_strategy_namespace(base)
    for key, value in winner_params.items():
        setattr(winner_namespace, key, value)
    test_algo = algorithm_for_id(
        options.strategy_id,
        **strategy_kwargs_from_namespace(options.strategy_id, winner_namespace),
    )
    test_result = run_backtest(
        test_algo,
        test_bars,
        initial_cash=options.cash,
        fee_rate=options.fee,
        slippage_rate=options.slippage,
        execution=options.execution,
    )
    benchmark_return = buy_and_hold_return_pct(
        test_bars,
        initial_cash=options.cash,
        fee_rate=options.fee,
        slippage_rate=options.slippage,
        execution=options.execution,
    )
    return {
        "csv": csv_label,
        "strategy_id": options.strategy_id,
        "bars": len(bars),
        "splits": {
            "train": len(train_bars),
            "validation": len(validation_bars),
            "test": len(test_bars),
        },
        "fee": options.fee,
        "slippage": options.slippage,
        "execution": options.execution,
        "selection": "validation_return_pct",
        "combos_tried": len(candidates),
        "skipped": skipped,
        "selected_params": winner_params,
        "candidates": candidates,
        "test": {
            **backtest_summary_dict(
                test_algo,
                test_result,
                bars=len(test_bars),
                extra={"strategy_id": options.strategy_id},
            ),
            "max_drawdown_pct": round(max_drawdown_pct(list(test_result.equity_curve)), 6),
            "buy_and_hold_return_pct": round(benchmark_return, 6),
            "excess_return_vs_buy_hold_pct": round(
                test_result.return_pct - benchmark_return,
                6,
            ),
        },
    }


@dataclass
class LeaderboardOptions(ResolvesCostRates):
    bars: list[dict[str, Any]]
    test_tail_bars: int = 100
    validation_fraction_of_pre_test: float = 0.25
    top_n: int = 3
    cash: float = 10.0
    fee: float | None = None
    slippage: float | None = None
    exchange: str | None = None
    execution: str = DEFAULT_BACKTEST_EXECUTION
    min_trades: int = 0
    max_combos: int = 64
    full_grid: bool = False
    strategy_ids: list[str] | None = None
    market_label: str = ""


def _split_fixed_test_tail(
    bars: list[dict[str, Any]],
    *,
    test_tail_bars: int,
    validation_fraction_of_pre_test: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    if test_tail_bars < 1:
        raise ValueError("test_tail_bars must be >= 1")
    if len(bars) <= test_tail_bars + 2:
        raise ValueError(
            f"need more than {test_tail_bars + 2} bars for train/validation/test (got {len(bars)})"
        )
    if not 0 < validation_fraction_of_pre_test < 1:
        raise ValueError("validation_fraction_of_pre_test must be in (0, 1)")
    test_bars = bars[-test_tail_bars:]
    pre_test = bars[:-test_tail_bars]
    validation_bars_count = max(1, int(len(pre_test) * validation_fraction_of_pre_test))
    if validation_bars_count >= len(pre_test):
        validation_bars_count = max(1, len(pre_test) // 4)
    train_bars = pre_test[:-validation_bars_count]
    validation_bars = pre_test[-validation_bars_count:]
    if len(train_bars) < 30:
        raise ValueError(f"train window too small ({len(train_bars)} bars); fetch more history")
    return train_bars, validation_bars, test_bars


def _best_params_for_strategy_on_splits(
    strategy_id: str,
    *,
    train_bars: list[dict[str, Any]],
    validation_bars: list[dict[str, Any]],
    base_namespace: Any | None,
    options: LeaderboardOptions,
) -> dict[str, Any]:
    param_grid = dict(tune_grid_for_strategy(strategy_id, full=options.full_grid))
    if not param_grid or len(param_grid) > MAX_SWEEP_PARAMS:
        param_grid = {}
    combos = list(itertools.product(*param_grid.values())) if param_grid else [tuple()]
    if len(combos) > options.max_combos:
        raise ValueError(f"{strategy_id}: grid has {len(combos)} combos; max is {options.max_combos}")
    base = merge_strategy_namespace(base_namespace)
    names = list(param_grid.keys())
    candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for combo in combos:
        namespace = merge_strategy_namespace(base)
        params = dict(zip(names, combo)) if names else {}
        for key, value in params.items():
            setattr(namespace, key, value)
        try:
            train_algo = algorithm_for_id(
                strategy_id,
                **strategy_kwargs_from_namespace(strategy_id, namespace),
            )
            train_result = run_backtest(
                train_algo,
                train_bars,
                initial_cash=options.cash,
                fee_rate=options.fee,
                slippage_rate=options.slippage,
                execution=options.execution,
            )
            validation_algo = algorithm_for_id(
                strategy_id,
                **strategy_kwargs_from_namespace(strategy_id, namespace),
            )
            validation_result = run_backtest(
                validation_algo,
                validation_bars,
                initial_cash=options.cash,
                fee_rate=options.fee,
                slippage_rate=options.slippage,
                execution=options.execution,
            )
        except ValueError as exc:
            skipped.append({"params": params, "error": str(exc)})
            continue
        candidates.append(
            {
                "params": params,
                "train_return_pct": train_result.return_pct,
                "validation_return_pct": validation_result.return_pct,
                "train_trades": len(train_result.trades),
                "validation_trades": len(validation_result.trades),
                "eligible": (
                    len(train_result.trades) >= options.min_trades
                    and len(validation_result.trades) >= options.min_trades
                ),
            }
        )

    if not candidates:
        reason = skipped[0]["error"] if skipped else "no combinations"
        raise ValueError(f"{strategy_id}: no valid param combos ({reason})")

    def _rank(row: dict[str, Any]) -> tuple[int, float, float]:
        return (
            1 if row["eligible"] else 0,
            float(row["validation_return_pct"]),
            float(row["train_return_pct"]),
        )

    candidates.sort(key=_rank, reverse=True)
    best = candidates[0]
    return {
        "strategy_id": strategy_id,
        "selected_params": best["params"],
        "validation_return_pct": best["validation_return_pct"],
        "train_return_pct": best["train_return_pct"],
        "combos_tried": len(candidates),
        "skipped": skipped,
    }


def run_leakage_safe_leaderboard(
    options: LeaderboardOptions,
    base_namespace: Any | None = None,
) -> dict[str, Any]:
    """
    Per strategy: tune on train, rank by validation return. Promote top ``top_n`` strategies;
    report test metrics on the held-out tail only (last ``test_tail_bars`` bars).
    """
    bars = list(options.bars)
    train_bars, validation_bars, test_bars = _split_fixed_test_tail(
        bars,
        test_tail_bars=options.test_tail_bars,
        validation_fraction_of_pre_test=options.validation_fraction_of_pre_test,
    )
    strategy_ids = list(options.strategy_ids or backtest_strategy_ids())
    scored: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for strategy_id in strategy_ids:
        try:
            scored.append(
                _best_params_for_strategy_on_splits(
                    strategy_id,
                    train_bars=train_bars,
                    validation_bars=validation_bars,
                    base_namespace=base_namespace,
                    options=options,
                )
            )
        except ValueError as exc:
            failures.append({"strategy_id": strategy_id, "error": str(exc)})

    if not scored:
        raise ValueError("no strategies produced validation scores")

    scored.sort(
        key=lambda row: (float(row["validation_return_pct"]), float(row["train_return_pct"])),
        reverse=True,
    )
    top_strategies = scored[: max(1, options.top_n)]
    benchmark_return = buy_and_hold_return_pct(
        test_bars,
        initial_cash=options.cash,
        fee_rate=options.fee,
        slippage_rate=options.slippage,
        execution=options.execution,
    )
    test_rows: list[dict[str, Any]] = []
    base = merge_strategy_namespace(base_namespace)
    for row in top_strategies:
        strategy_id = row["strategy_id"]
        namespace = merge_strategy_namespace(base)
        for key, value in row["selected_params"].items():
            setattr(namespace, key, value)
        test_algo = algorithm_for_id(
            strategy_id,
            **strategy_kwargs_from_namespace(strategy_id, namespace),
        )
        test_result = run_backtest(
            test_algo,
            test_bars,
            initial_cash=options.cash,
            fee_rate=options.fee,
            slippage_rate=options.slippage,
            execution=options.execution,
        )
        test_rows.append(
            {
                "strategy_id": strategy_id,
                "selected_params": row["selected_params"],
                "validation_return_pct": row["validation_return_pct"],
                "test": {
                    **backtest_summary_dict(
                        test_algo,
                        test_result,
                        bars=len(test_bars),
                        extra={"strategy_id": strategy_id},
                    ),
                    "max_drawdown_pct": round(max_drawdown_pct(list(test_result.equity_curve)), 6),
                    "excess_return_vs_buy_hold_pct": round(
                        test_result.return_pct - benchmark_return,
                        6,
                    ),
                },
            }
        )

    return {
        "market": options.market_label,
        "bars_total": len(bars),
        "resolution_note": "chronological train → validation → test (no test peeking)",
        "splits": {
            "train": len(train_bars),
            "validation": len(validation_bars),
            "test": len(test_bars),
        },
        "cash": options.cash,
        "fee": options.fee,
        "slippage": options.slippage,
        "execution": options.execution,
        "selection": "validation_return_pct_after_train_tune",
        "all_strategies_validation_ranking": scored,
        "failures": failures,
        "top_n": options.top_n,
        "test_buy_and_hold_return_pct": round(benchmark_return, 6),
        "top_strategies_test": test_rows,
    }
