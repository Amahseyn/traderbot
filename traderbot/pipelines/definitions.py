from __future__ import annotations

import json
from pathlib import Path

from traderbot.algorithms.registry import algorithm_for_id, backtest_strategy_ids
from traderbot.algorithms.visualize import compare_visualization_paths_to_dict, render_compare_plots
from traderbot.backtesting import backtest_summary_dict, load_bars_csv, run_backtest, save_backtest_result
from traderbot.backtesting.holdout_window import return_pct_over_equity_tail
from traderbot.data.export import load_jobs, run_export, write_csv
from traderbot.data.crypto_store import resolve_crypto_1h_csv_paths
from traderbot.results.layout import result_tree_at
from traderbot.utils.bars import bars_last_n
from traderbot.markets.registry import DEFAULT_JOBS_PATH
from traderbot.pipelines.base import PipelineResult
from traderbot.solutions.layout import SOLUTIONS_ROOT, prepare_solution

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CRYPTO_DATA = REPO_ROOT / "data" / "crypto"


def pipeline_crypto_jobs_export(
    *,
    data_dir: Path | None = None,
    jobs_file: Path = DEFAULT_JOBS_PATH,
    days = 30,
    solutions_root: Path = SOLUTIONS_ROOT,
    solution_root: Path | None = None,
) -> PipelineResult:
    """Download OHLC for every job in the export jobs file → CSV."""
    layout = prepare_solution(
        "crypto-jobs-export",
        solutions_root=solutions_root,
        solution_root=solution_root,
        title="Crypto jobs export",
        description=f"Nobitex OHLC from {jobs_file.name}.",
    )
    from traderbot.data.crypto_store import crypto_ohlc_dir

    crypto_root = data_dir or DEFAULT_CRYPTO_DATA
    ohlc_dir = crypto_ohlc_dir(crypto_root)
    ohlc_dir.mkdir(parents=True, exist_ok=True)

    result = PipelineResult(pipeline_id="crypto-jobs-export")
    jobs = load_jobs(jobs_file)
    written = run_export(
        jobs,
        days=days,
        output_dir=crypto_root,
        to_ts=None,
        crypto_layout=True,
    )
    manifest = crypto_root / "export_manifest.json"
    if manifest.is_file():
        (layout.reports / "export_manifest.json").write_text(
            manifest.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    result.add_step(
        "export",
        detail=f"{len(written)} CSV files from {jobs_file.name}",
        artifacts=written + [manifest, layout.root / "README.md"],
    )
    result.outputs = {
        "solution_root": str(layout.root),
        "data_dir": str(ohlc_dir),
        "crypto_root": str(crypto_root),
        "csv_count": len(written),
        "manifest": str(layout.reports / "export_manifest.json"),
    }
    result.write_summary(layout.reports / "pipeline_summary.json")
    return result


def pipeline_sma_backtest(
    *,
    csv_path: Path,
    results_dir: Path | None = None,
    fast = 5,
    slow = 20,
    strategy_id = "sma_cross",
    solutions_root: Path = SOLUTIONS_ROOT,
) -> PipelineResult:
    """OHLC CSV → rule-based strategy backtest summary JSON."""
    layout = prepare_solution(
        "sma-backtest",
        solutions_root=solutions_root,
        solution_root=results_dir,
        title="Strategy backtest",
        description=f"{strategy_id} on {csv_path.name}.",
    )
    result = PipelineResult(pipeline_id="sma-backtest")
    bars = load_bars_csv(csv_path)
    algo = algorithm_for_id(strategy_id, fast=fast, slow=slow)
    bt = run_backtest(algo, bars)
    run_name = f"{csv_path.stem}_{strategy_id}_{fast}_{slow}"
    run_out = layout.run_dir_flat(run_name)
    summary_path = run_out / "backtest_summary.json"
    payload = {
        "strategy_id": strategy_id,
        "return_pct": bt.return_pct,
        "initial_cash": bt.initial_cash,
        "final_equity": bt.final_equity,
        "trade_count": len(bt.trades),
    }
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    result.add_step("backtest", detail=f"return {bt.return_pct:.2f}%", artifacts=[summary_path])
    result.outputs = {"solution_root": str(layout.root), **payload}
    result.write_summary(layout.reports / "pipeline_summary.json")
    return result


def _run_crypto_1h_local_for_csv(
    *,
    source_csv: Path,
    layout,
    tail_bars: int | None,
    holdout_tail_bars: int | None,
    initial_cash: float,
) -> dict:
    if not source_csv.is_file():
        raise FileNotFoundError(f"1h OHLC CSV not found: {source_csv}; export or pass --csv/--symbol")

    all_bars = load_bars_csv(source_csv)
    if tail_bars is not None:
        bars = bars_last_n(all_bars, tail_bars)
        slice_label = f"last{tail_bars}h"
    else:
        bars = all_bars
        if holdout_tail_bars is not None:
            slice_label = f"full_holdout{holdout_tail_bars}h"
        else:
            slice_label = "full"
    if not bars:
        raise ValueError(f"no bars in {source_csv}")

    slice_path = layout.data / f"{source_csv.stem}_{slice_label}.csv"
    slice_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(slice_path, bars)

    ranked: list[dict] = []
    equity_by_strategy: dict[str, list[tuple[int, float]]] = {}
    compare_root = layout.runs / "strategy_compare" / source_csv.stem
    tree = result_tree_at(compare_root, run_id=slice_path.stem)
    for strategy_id in backtest_strategy_ids():
        algo = algorithm_for_id(strategy_id)
        from traderbot.utils.trading_costs import (
            DEFAULT_BACKTEST_EXECUTION,
            DEFAULT_SLIPPAGE_RATE,
            DEFAULT_TRADE_FEE_RATE,
        )

        backtest_result = run_backtest(
            algo,
            bars,
            initial_cash=initial_cash,
            fee_rate=DEFAULT_TRADE_FEE_RATE,
            slippage_rate=DEFAULT_SLIPPAGE_RATE,
            execution=DEFAULT_BACKTEST_EXECUTION,
        )
        equity_by_strategy[strategy_id] = list(backtest_result.equity_curve)
        extra_row: dict = {"strategy_id": strategy_id}
        if holdout_tail_bars is not None:
            holdout_return = return_pct_over_equity_tail(
                list(backtest_result.equity_curve),
                holdout_tail_bars,
            )
            if holdout_return is not None:
                extra_row["holdout_return_pct"] = round(holdout_return, 6)
        row = backtest_summary_dict(
            algo,
            backtest_result,
            bars=len(bars),
            extra=extra_row,
        )
        ranked.append(row)
        run_dir = tree.run_dir_flat(strategy_id)
        save_backtest_result(
            algo,
            backtest_result,
            run_dir,
            bars=len(bars),
            bar_rows=bars,
            visualize=True,
            extra={"strategy_id": strategy_id, "csv": str(slice_path)},
        )

    if holdout_tail_bars is not None:
        ranked.sort(
            key=lambda row: row.get("holdout_return_pct", row["return_pct"]),
            reverse=True,
        )
    else:
        ranked.sort(key=lambda row: row["return_pct"], reverse=True)
    compare_payload: dict = {
        "csv": str(slice_path),
        "source_csv": str(source_csv),
        "bars": len(bars),
        "tail_bars": tail_bars,
        "holdout_tail_bars": holdout_tail_bars,
        "bars_available": len(all_bars),
        "best_strategy_id": ranked[0]["strategy_id"] if ranked else None,
        "strategies": ranked,
    }
    try:
        compare_paths = render_compare_plots(
            asset_label=slice_path.stem,
            bars=bars,
            initial_cash=initial_cash,
            ranked_rows=ranked,
            equity_by_strategy=equity_by_strategy,
            out_dir=compare_root,
        )
        compare_payload["visualization"] = compare_visualization_paths_to_dict(compare_paths)
    except ImportError:
        pass
    manifest_path = tree.reports / "compare_manifest.json"
    manifest_path.write_text(json.dumps(compare_payload, indent=2), encoding="utf-8")

    return {
        "symbol": source_csv.stem.removesuffix("_60"),
        "source_csv": str(source_csv),
        "slice_csv": str(slice_path),
        "bar_count": len(bars),
        "bars_available": len(all_bars),
        "tail_bars": tail_bars,
        "holdout_tail_bars": holdout_tail_bars,
        "compare_manifest": str(manifest_path),
        "best_strategy_id": compare_payload["best_strategy_id"],
        "slice_artifact": slice_path,
        "compare_artifact": manifest_path,
    }


def pipeline_crypto_1h_local(
    *,
    csv_path: Path | None = None,
    symbol: str | None = None,
    all_assets: bool = False,
    tail_bars: int | None = None,
    holdout_tail_bars: int | None = None,
    results_dir: Path | None = None,
    solutions_root: Path = SOLUTIONS_ROOT,
    initial_cash = 10_000.0,
    horizon: str = "1h",
) -> PipelineResult:
    """On-disk 1h OHLC → compare rule-based strategies (optional tail_bars slice or holdout_tail_bars)."""
    layout = prepare_solution(
        "crypto-1h-local",
        solutions_root=solutions_root,
        solution_root=results_dir,
        title="Crypto 1h local",
        description="No export; last N one-hour bars per asset from existing OHLC CSVs.",
    )
    result = PipelineResult(pipeline_id="crypto-1h-local")
    source_csvs = resolve_crypto_1h_csv_paths(
        csv_path=csv_path,
        symbol=symbol,
        all_assets=all_assets,
    )

    asset_outputs: list[dict] = []
    for source_csv in source_csvs:
        asset_result = _run_crypto_1h_local_for_csv(
            source_csv=source_csv,
            layout=layout,
            tail_bars=tail_bars,
            holdout_tail_bars=holdout_tail_bars,
            initial_cash=initial_cash,
        )
        result.add_step(
            "slice",
            detail=f"{asset_result['bar_count']} bars from {Path(asset_result['source_csv']).name}",
            artifacts=[asset_result["slice_artifact"]],
        )
        result.add_step(
            "strategy_compare",
            detail=f"{asset_result['symbol']}: best {asset_result['best_strategy_id']}",
            artifacts=[asset_result["compare_artifact"]],
        )
        asset_outputs.append({k: v for k, v in asset_result.items() if not k.endswith("_artifact")})

    result.outputs = {
        "solution_root": str(layout.root),
        "tail_bars": tail_bars,
        "asset_count": len(asset_outputs),
        "assets": asset_outputs,
    }
    if len(asset_outputs) == 1:
        result.outputs.update(asset_outputs[0])

    result.write_summary(layout.reports / "pipeline_summary.json")
    return result



def pipeline_export_then_hourly(
    *,
    pipeline_id: str,
    title: str,
    description: str,
    data_dir: Path | None = None,
    results_dir: Path | None = None,
    export_days = 30,
    horizon: str = "1h",
    all_assets: bool = True,
    csv_path: Path | None = None,
    solutions_root: Path = SOLUTIONS_ROOT,
) -> PipelineResult:
    """Export crypto 1h jobs file, then compare strategies on each hourly file."""
    layout = prepare_solution(
        pipeline_id,
        solutions_root=solutions_root,
        solution_root=results_dir,
        title=title,
        description=description,
    )
    result = PipelineResult(pipeline_id=pipeline_id)
    csv_dir = data_dir or layout.data
    exported = pipeline_crypto_jobs_export(
        data_dir=csv_dir,
        days=export_days,
        solutions_root=solutions_root,
        solution_root=layout.root,
    )
    result.steps.extend(exported.steps)
    desk = pipeline_crypto_1h_local(
        csv_path=None if all_assets else csv_path,
        all_assets=all_assets,
        horizon=horizon,
        results_dir=layout.root,
        solutions_root=solutions_root,
    )
    result.steps.extend(desk.steps)
    result.outputs = {
        "solution_root": str(layout.root),
        "data_dir": str(csv_dir),
        "asset_count": desk.outputs.get("asset_count"),
    }
    result.write_summary(layout.reports / "pipeline_summary.json")
    return result

