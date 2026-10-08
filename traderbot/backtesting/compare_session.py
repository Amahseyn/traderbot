from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traderbot.algorithms.registry import (
    algorithm_for_id,
    backtest_strategy_ids,
    normalize_strategy_mode,
    strategy_ids_for_mode,
    strategy_kwargs_from_namespace,
)
from traderbot.algorithms.optimized_params import resolve_optimized_namespace
from traderbot.algorithms.visualize import (
    compare_visualization_paths_to_dict,
    render_compare_plots,
)
from traderbot.backtesting import backtest_summary_dict, load_bars_csv, run_backtest, save_backtest_result
from traderbot.backtesting import vectorbt_extra_for_backtest
from traderbot.data.intrahour import enrich_bars_for_csv
from traderbot.utils.resolution import resolution_from_csv_path, resolution_minutes
from traderbot.utils.bars import filter_bars_by_unix_range
from traderbot.results.layout import (
    default_strategy_batch_out,
    default_strategy_compare_out,
    result_tree_at,
)
from traderbot.utils.trading_costs import (
    DEFAULT_BACKTEST_EXECUTION,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_TRADE_FEE_RATE,
)


def strategy_compare_plan(_mode: str | None) -> list[tuple[str, str, dict[str, Any]]]:
    """Rows for strategy compare: (result id, algorithm id, extra kwargs)."""
    return [(strategy_id, strategy_id, {}) for strategy_id in backtest_strategy_ids()]


LogFn = Callable[[str], None]


@dataclass
class StrategyCompareOptions:
    csv_path: Path
    out_dir: Path | None = None
    visualize: bool = True
    cash: float = 10_000.0
    fee: float = DEFAULT_TRADE_FEE_RATE
    slippage: float = DEFAULT_SLIPPAGE_RATE
    execution: str = DEFAULT_BACKTEST_EXECUTION
    vectorbt: bool = False
    strategy_namespace: Any | None = None
    mode: str = "strategies"
    strategy_ids: frozenset[str] | None = None
    max_strategies: int | None = None
    run_start_unix_seconds: int | None = None
    run_end_unix_seconds: int | None = None
    use_optimized_strategy_params: bool = True


def _log(log: LogFn | None, message: str) -> None:
    if log is not None:
        log(message)
    else:
        import sys

        print(message, file=sys.stderr, flush=True)


def _vectorbt_extra(algo, bars: list[dict], options: StrategyCompareOptions) -> dict[str, Any]:
    if not options.vectorbt:
        return {}
    extra = vectorbt_extra_for_backtest(
        algo,
        bars,
        initial_cash=options.cash,
        fee_rate=options.fee,
        slippage_rate=options.slippage,
    )
    return extra or {}


def _algorithm_kwargs(strategy_id: str, options: StrategyCompareOptions) -> dict[str, Any]:
    if options.use_optimized_strategy_params:
        namespace = resolve_optimized_namespace(
            strategy_id,
            options.strategy_namespace,
            csv_path=options.csv_path,
        )
    else:
        from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest

        namespace = namespace_for_strategy_backtest(
            strategy_id,
            options.strategy_namespace,
            csv_path=options.csv_path,
        )
    return strategy_kwargs_from_namespace(strategy_id, namespace)


def run_strategy_compare(options: StrategyCompareOptions, *, log: LogFn | None = None) -> dict[str, Any]:
    csv_path = options.csv_path.resolve()
    raw_bars = enrich_bars_for_csv(load_bars_csv(csv_path), csv_path, options.strategy_namespace)
    if not raw_bars:
        raise ValueError(f"No bars in CSV: {csv_path}")
    bars = raw_bars
    resolution = resolution_from_csv_path(csv_path.name)
    bar_minutes = resolution_minutes(resolution) or 60
    bars = filter_bars_by_unix_range(
        bars,
        start_unix_seconds=options.run_start_unix_seconds,
        end_unix_seconds=options.run_end_unix_seconds,
        bar_minutes=bar_minutes,
    )
    if not bars:
        window_label = f"{options.run_start_unix_seconds}..{options.run_end_unix_seconds}"
        file_label = f"{raw_bars[0]['timestamp']}..{raw_bars[-1]['timestamp']}"
        raise ValueError(
            f"No bars in CSV after run window {window_label} (file covers {file_label}): {csv_path}"
        )

    mode = normalize_strategy_mode(options.mode)
    plan = strategy_compare_plan(mode)
    if options.strategy_ids:
        plan = [entry for entry in plan if entry[0] in options.strategy_ids]
    if options.max_strategies is not None:
        if options.max_strategies < 1:
            raise ValueError("max_strategies must be at least 1")
        plan = plan[: options.max_strategies]
    if not plan:
        raise ValueError("no strategies selected for compare")
    ranked: list[dict[str, Any]] = []
    equity_by_strategy: dict[str, list[tuple[int, float]]] = {}
    compare_root = options.out_dir
    if compare_root is None and options.visualize:
        compare_root = default_strategy_compare_out(csv_path)
    tree = result_tree_at(compare_root, run_id=csv_path.stem) if compare_root is not None else None
    viz = compare_root is not None and options.visualize
    compare_session_id = str(uuid.uuid4())
    _log(log, f"compare: {mode} mode, {len(plan)} strategies on {csv_path.name} ({len(bars)} bars, {options.execution} fills)")

    for index, (strategy_id, algorithm_id, extra) in enumerate(plan, start=1):
        _log(log, f"compare: [{index}/{len(plan)}] {strategy_id}")
        kwargs = _algorithm_kwargs(algorithm_id, options)
        kwargs.update(extra)
        algo = algorithm_for_id(algorithm_id, **kwargs)
        result = run_backtest(
            algo,
            bars,
            initial_cash=options.cash,
            fee_rate=options.fee,
            slippage_rate=options.slippage,
            execution=options.execution,
        )
        equity_by_strategy[strategy_id] = list(result.equity_curve)
        row = backtest_summary_dict(
            algo,
            result,
            bars=len(bars),
            extra={"strategy_id": strategy_id, **_vectorbt_extra(algo, bars, options)},
        )
        ranked.append(row)
        _log(
            log,
            f"compare: [{index}/{len(plan)}] {strategy_id} return {row['return_pct']}%",
        )
        if tree is not None:
            run_dir = tree.run_dir_flat(strategy_id)
            save_backtest_result(
                algo,
                result,
                run_dir,
                bars=len(bars),
                bar_rows=bars,
                visualize=viz,
                extra={
                    "strategy_id": strategy_id,
                    "csv": str(csv_path),
                    "compare_session_id": compare_session_id,
                    **_vectorbt_extra(algo, bars, options),
                },
            )

    ranked.sort(key=lambda row: row["return_pct"], reverse=True)
    best = ranked[0] if ranked else None
    payload: dict[str, Any] = {
        "csv": str(csv_path),
        "bars": len(bars),
        "mode": mode,
        "cash": options.cash,
        "fee": options.fee,
        "slippage": options.slippage,
        "execution": options.execution,
        "best_strategy_id": best["strategy_id"] if best else None,
        "strategies": ranked,
    }
    if tree is not None:
        if viz:
            _log(log, "compare: rendering charts")
            try:
                compare_paths = render_compare_plots(
                    asset_label=csv_path.stem,
                    bars=bars,
                    initial_cash=options.cash,
                    ranked_rows=ranked,
                    equity_by_strategy=equity_by_strategy,
                    out_dir=compare_root,
                )
                payload["visualization"] = compare_visualization_paths_to_dict(compare_paths)
            except ImportError:
                pass
        manifest_path = tree.reports / "compare_manifest.json"
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        payload["manifest"] = str(manifest_path)
        payload["compare_session_id"] = compare_session_id
        from traderbot.recording import try_record

        try_record("compare_session", compare_payload=payload)

    _log(log, json.dumps(payload, indent=2))
    return payload


@dataclass
class StrategyTestOptions:
    csv_path: Path
    strategy_id: str
    out_dir: Path | None = None
    visualize: bool = True
    cash: float = 10_000.0
    fee: float = DEFAULT_TRADE_FEE_RATE
    slippage: float = DEFAULT_SLIPPAGE_RATE
    execution: str = DEFAULT_BACKTEST_EXECUTION
    vectorbt: bool = False
    strategy_namespace: Any | None = None
    mode: str = "strategies"


def run_strategy_test(options: StrategyTestOptions, *, log: LogFn | None = None) -> dict[str, Any]:
    """Backtest one rule-based strategy."""
    mode = normalize_strategy_mode(options.mode)
    if options.strategy_id not in strategy_ids_for_mode(mode):
        raise ValueError(f"strategy {options.strategy_id!r} is not available in {mode} mode")

    compare_options = StrategyCompareOptions(
        csv_path=options.csv_path,
        cash=options.cash,
        fee=options.fee,
        slippage=options.slippage,
        execution=options.execution,
        vectorbt=options.vectorbt,
        strategy_namespace=options.strategy_namespace,
        mode=mode,
    )
    csv_path = options.csv_path.resolve()
    bars = enrich_bars_for_csv(load_bars_csv(csv_path), csv_path, options.strategy_namespace)
    if not bars:
        raise ValueError(f"No bars in CSV: {csv_path}")

    _log(log, f"strategy test: {mode} mode, {options.strategy_id} on {csv_path.name} ({len(bars)} bars, {compare_options.execution} fills)")
    kwargs = _algorithm_kwargs(options.strategy_id, compare_options)
    algo = algorithm_for_id(options.strategy_id, **kwargs)
    result = run_backtest(
        algo,
        bars,
        initial_cash=options.cash,
        fee_rate=options.fee,
        slippage_rate=options.slippage,
        execution=options.execution,
    )
    summary = backtest_summary_dict(
        algo,
        result,
        bars=len(bars),
        extra={
            "strategy_id": options.strategy_id,
            "mode": mode,
            **_vectorbt_extra(algo, bars, compare_options),
        },
    )
    out_dir = options.out_dir or (default_strategy_batch_out(options.strategy_id) / csv_path.stem)
    tree = result_tree_at(out_dir, run_id=options.strategy_id)
    run_dir = tree.run_dir_flat(options.strategy_id)
    save_backtest_result(
        algo,
        result,
        run_dir,
        bars=len(bars),
        bar_rows=bars,
        visualize=options.visualize,
        extra={"strategy_id": options.strategy_id, "csv": str(csv_path), "mode": mode},
    )
    summary["run_dir"] = str(run_dir)
    _log(log, json.dumps(summary, indent=2))
    return summary
