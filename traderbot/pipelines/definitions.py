from __future__ import annotations

import json
from pathlib import Path

from traderbot.algorithms.registry import algorithm_for_id, implemented_strategy_ids
from traderbot.algorithms.visualize import compare_visualization_paths_to_dict, render_compare_plots
from traderbot.backtesting import backtest_summary_dict, load_bars_csv, run_backtest, save_backtest_result
from traderbot.data.export import load_jobs, run_export, write_csv
from traderbot.data.crypto_store import resolve_crypto_1h_csv_paths, resolve_crypto_data_dir
from traderbot.ml.intervals import default_eval_horizon, min_bars_for_forecast_eval
from traderbot.ml.models.lightgbm import LightGBMForecastModel
from traderbot.results.layout import result_tree_at
from traderbot.utils.bars import bars_last_n
from traderbot.utils.constants import DEFAULT_LIGHTGBM_NUM_BOOST_ROUND, DEFAULT_ML_TRAIN_RATIO
from traderbot.ml.batch import run_batch_on_directory
from traderbot.ml.pipeline import model_for_id, run_forecast_eval
from traderbot.ml.results import save_run_result
from traderbot.pipelines.base import PipelineResult
from traderbot.solutions.layout import SOLUTIONS_ROOT, prepare_solution

REPO_ROOT = Path(__file__).resolve().parents[2]
JOBS_FIVE_SOURCES = REPO_ROOT / "export.jobs.5sources.json"
DEFAULT_CRYPTO_DATA = REPO_ROOT / "data" / "crypto"


def pipeline_multisource_export(
    *,
    data_dir: Path | None = None,
    jobs_file: Path = JOBS_FIVE_SOURCES,
    days = 30,
    solutions_root: Path = SOLUTIONS_ROOT,
    solution_root: Path | None = None,
) -> PipelineResult:
    """Download OHLC for five markets and all job intervals → CSV."""
    layout = prepare_solution(
        "multisource-export",
        solutions_root=solutions_root,
        solution_root=solution_root,
        title="Multisource export",
        description="Nobitex OHLC for five markets (see export.jobs.5sources.json).",
    )
    from traderbot.data.crypto_store import crypto_ohlc_dir

    crypto_root = data_dir or DEFAULT_CRYPTO_DATA
    ohlc_dir = crypto_ohlc_dir(crypto_root)
    ohlc_dir.mkdir(parents=True, exist_ok=True)

    result = PipelineResult(pipeline_id="multisource-export")
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


def pipeline_lightgbm_multisource(
    *,
    data_dir: Path | None = None,
    results_dir: Path | None = None,
    all_horizons = False,
    skip_export = True,
    jobs_file: Path = JOBS_FIVE_SOURCES,
    export_days = 30,
    solutions_root: Path = SOLUTIONS_ROOT,
) -> PipelineResult:
    """Export (optional) → LightGBM batch → plots + manifest under ``solutions/``."""
    pid = "lightgbm-multisource-all-horizons" if all_horizons else "lightgbm-multisource-default"
    title = "LightGBM multisource (all horizons)" if all_horizons else "LightGBM multisource (1h default)"
    layout = prepare_solution(
        pid,
        solutions_root=solutions_root,
        solution_root=results_dir,
        title=title,
        description="Batch LightGBM eval with standard solution layout.",
    )
    result = PipelineResult(pipeline_id=pid)
    from traderbot.data.crypto_store import crypto_ohlc_dir, resolve_crypto_data_dir

    csv_dir = data_dir or resolve_crypto_data_dir() or crypto_ohlc_dir(DEFAULT_CRYPTO_DATA)

    if not skip_export:
        exp = pipeline_multisource_export(
            data_dir=data_dir or DEFAULT_CRYPTO_DATA,
            jobs_file=jobs_file,
            days=export_days,
            solutions_root=solutions_root,
            solution_root=layout.root,
        )
        result.steps.extend(exp.steps)

    if not csv_dir.is_dir() or not list(csv_dir.glob("*.csv")):
        raise FileNotFoundError(f"no CSV in {csv_dir}; export first or pass data_dir")

    runs = run_batch_on_directory(
        csv_dir,
        layout=layout,
        model_id="lightgbm",
        all_horizons=all_horizons,
        num_boost_round=50,
    )
    manifest = layout.reports / "batch_manifest.json"
    result.add_step(
        "lightgbm_batch",
        detail=f"{len(runs)} eval runs (all_horizons={all_horizons})",
        artifacts=[manifest, layout.root],
    )
    result.outputs = {
        "solution_root": str(layout.root),
        "data_dir": str(csv_dir),
        "runs_dir": str(layout.runs),
        "reports_dir": str(layout.reports),
        "run_count": len(runs),
        "batch_manifest": str(manifest),
    }
    result.write_summary(layout.reports / "pipeline_summary.json")
    return result


def pipeline_lightgbm_single_asset(
    *,
    csv_path: Path,
    results_dir: Path | None = None,
    all_horizons = True,
    solutions_root: Path = SOLUTIONS_ROOT,
) -> PipelineResult:
    """One OHLC CSV → LightGBM for default horizon(s) with visualizations."""
    from traderbot.ml.intervals import (
        default_eval_horizon,
        forecast_horizons_for_resolution,
        min_bars_for_forecast_eval,
        resolution_from_csv_path,
        resolution_minutes,
    )
    from traderbot.ml.models.lightgbm import LightGBMForecastModel

    layout = prepare_solution(
        "lightgbm-single-asset",
        solutions_root=solutions_root,
        solution_root=results_dir,
        title="LightGBM single asset",
        description=f"All default horizons for {csv_path.name}.",
    )
    result = PipelineResult(pipeline_id="lightgbm-single-asset")
    bars = load_bars_csv(csv_path)
    resolution = resolution_from_csv_path(csv_path.name)
    bar_minutes = resolution_minutes(resolution)
    if all_horizons:
        specs = forecast_horizons_for_resolution(resolution)
    else:
        hb, _ = default_eval_horizon(resolution)
        specs = [(hb, "")]

    model = LightGBMForecastModel(num_boost_round=50)
    run_dirs: list[str] = []
    for horizon_bars, _ in specs:
        if len(bars) < min_bars_for_forecast_eval(horizon_bars):
            continue
        eval_result = run_forecast_eval(
            bars,
            model,
            horizon_bars=horizon_bars,
            bar_minutes=bar_minutes,
        )
        out = layout.run_dir(csv_path.stem, eval_result.horizon_label)
        save_run_result(eval_result, out)
        run_dirs.append(str(out))

    result.add_step("lightgbm_eval", detail=f"{len(run_dirs)} horizon runs", artifacts=run_dirs)
    result.outputs = {
        "solution_root": str(layout.root),
        "csv": str(csv_path),
        "runs": run_dirs,
    }
    result.write_summary(layout.reports / "pipeline_summary.json")
    return result


def pipeline_chronos_single(
    *,
    csv_path: Path,
    results_dir: Path | None = None,
    horizon_bars = 4,
    bar_minutes = 60,
    solutions_root: Path = SOLUTIONS_ROOT,
) -> PipelineResult:
    """Single asset → Chronos pretrained eval (requires ``.[chronos]``)."""
    layout = prepare_solution(
        "chronos-single",
        solutions_root=solutions_root,
        solution_root=results_dir,
        title="Chronos single asset",
        description=f"Chronos forecast on {csv_path.name}.",
    )
    result = PipelineResult(pipeline_id="chronos-single")
    bars = load_bars_csv(csv_path)
    model = model_for_id("chronos")
    eval_result = run_forecast_eval(
        bars,
        model,
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
    )
    out = layout.run_dir(csv_path.stem, eval_result.horizon_label)
    save_run_result(eval_result, out)
    result.add_step("chronos_eval", artifacts=[out / "results.json", out / "visualizations"])
    result.outputs = {"solution_root": str(layout.root), "run_dir": str(out), "metrics": eval_result.metrics}
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
    initial_cash: float,
    run_lightgbm: bool,
    model_id: str = "lightgbm",
    train_ratio = DEFAULT_ML_TRAIN_RATIO,
    train_supervised_row_count: int | None = None,
    num_boost_round = DEFAULT_LIGHTGBM_NUM_BOOST_ROUND,
) -> dict:
    if not source_csv.is_file():
        raise FileNotFoundError(f"1h OHLC CSV not found: {source_csv}; export or pass --csv/--symbol")

    all_bars = load_bars_csv(source_csv)
    if tail_bars is None:
        bars = all_bars
        slice_label = "full"
    else:
        bars = bars_last_n(all_bars, tail_bars)
        slice_label = f"last{tail_bars}h"
    if not bars:
        raise ValueError(f"no bars in {source_csv}")

    slice_path = layout.data / f"{source_csv.stem}_{slice_label}.csv"
    slice_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(slice_path, bars)

    ranked: list[dict] = []
    equity_by_strategy: dict[str, list[tuple[int, float]]] = {}
    compare_root = layout.runs / "strategy_compare" / source_csv.stem
    tree = result_tree_at(compare_root, run_id=slice_path.stem)
    for strategy_id in implemented_strategy_ids():
        algo = algorithm_for_id(strategy_id)
        backtest_result = run_backtest(algo, bars, initial_cash=initial_cash, fee_rate=0.0)
        equity_by_strategy[strategy_id] = list(backtest_result.equity_curve)
        row = backtest_summary_dict(
            algo,
            backtest_result,
            bars=len(bars),
            extra={"strategy_id": strategy_id},
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
    ranked.sort(key=lambda row: row["return_pct"], reverse=True)
    compare_payload: dict = {
        "csv": str(slice_path),
        "source_csv": str(source_csv),
        "bars": len(bars),
        "tail_bars": tail_bars,
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

    lightgbm_run_dir: str | None = None
    lightgbm_out = None
    lightgbm_step: tuple[str, str] | None = None
    supervised_row_count: int | None = None
    train_supervised_rows_trained: int | None = None
    test_supervised_row_count: int | None = None
    horizon_bars, bar_minutes = default_eval_horizon("60")
    min_bars = min_bars_for_forecast_eval(
        horizon_bars,
        train_ratio=train_ratio,
        train_supervised_row_count=train_supervised_row_count,
    )
    if run_lightgbm and len(bars) >= min_bars:
        if model_id != "lightgbm":
            raise ValueError(
                f"crypto-1h-local supports model_id='lightgbm' only; got {model_id!r}",
            )
        model = model_for_id(model_id, num_boost_round=num_boost_round)
        eval_result = run_forecast_eval(
            bars,
            model,
            horizon_bars=horizon_bars,
            bar_minutes=bar_minutes,
            train_ratio=train_ratio,
            train_supervised_row_count=train_supervised_row_count,
        )
        lightgbm_out = layout.run_dir(source_csv.stem, eval_result.horizon_label)
        save_run_result(eval_result, lightgbm_out)
        lightgbm_run_dir = str(lightgbm_out)
        lightgbm_step = ("lightgbm", eval_result.horizon_label)
        train_supervised_rows_trained = eval_result.extra.get("train_supervised_row_count")
        test_supervised_row_count = eval_result.extra.get("test_supervised_row_count")
        supervised_row_count = eval_result.extra.get("supervised_row_count")
    elif run_lightgbm:
        lightgbm_step = ("lightgbm_skipped", f"need >={min_bars} bars for eval, have {len(bars)}")

    return {
        "symbol": source_csv.stem.removesuffix("_60"),
        "source_csv": str(source_csv),
        "slice_csv": str(slice_path),
        "bar_count": len(bars),
        "bars_available": len(all_bars),
        "tail_bars": tail_bars,
        "min_bars_lightgbm": min_bars,
        "lightgbm_ran": lightgbm_run_dir is not None,
        "compare_manifest": str(manifest_path),
        "best_strategy_id": compare_payload["best_strategy_id"],
        "model_id": model_id,
        "train_supervised_row_count": train_supervised_row_count,
        "train_supervised_rows_trained": train_supervised_rows_trained,
        "num_boost_round": num_boost_round,
        "supervised_row_count": supervised_row_count,
        "test_supervised_row_count": test_supervised_row_count,
        "lightgbm_run_dir": lightgbm_run_dir,
        "lightgbm_step": lightgbm_step,
        "slice_artifact": slice_path,
        "compare_artifact": manifest_path,
        "lightgbm_artifact": lightgbm_out if lightgbm_run_dir else None,
    }


def pipeline_crypto_1h_local(
    *,
    csv_path: Path | None = None,
    symbol: str | None = None,
    all_assets: bool = False,
    tail_bars: int | None = None,
    results_dir: Path | None = None,
    solutions_root: Path = SOLUTIONS_ROOT,
    initial_cash = 10_000.0,
    run_lightgbm = True,
    model_id = "lightgbm",
    train_ratio = DEFAULT_ML_TRAIN_RATIO,
    train_supervised_row_count: int | None = None,
    num_boost_round = DEFAULT_LIGHTGBM_NUM_BOOST_ROUND,
) -> PipelineResult:
    """On-disk 1h OHLC → compare all strategies per asset; optional LightGBM (uses full CSV unless tail_bars set)."""
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
            initial_cash=initial_cash,
            run_lightgbm=run_lightgbm,
            model_id=model_id,
            train_ratio=train_ratio,
            train_supervised_row_count=train_supervised_row_count,
            num_boost_round=num_boost_round,
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
        if asset_result["lightgbm_step"] is not None:
            step_name, step_detail = asset_result["lightgbm_step"]
            artifacts = [asset_result["lightgbm_artifact"]] if asset_result["lightgbm_artifact"] else []
            result.add_step(step_name, detail=f"{asset_result['symbol']}: {step_detail}", artifacts=artifacts)
        asset_outputs.append({k: v for k, v in asset_result.items() if not k.endswith("_artifact") and k != "lightgbm_step"})

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



def pipeline_full_research(
    *,
    data_dir: Path | None = None,
    results_dir: Path | None = None,
    export_days = 90,
    solutions_root: Path = SOLUTIONS_ROOT,
) -> PipelineResult:
    """Full stack: 5-source export → LightGBM all default horizons → summary."""
    layout = prepare_solution(
        "full-research-lightgbm",
        solutions_root=solutions_root,
        solution_root=results_dir,
        title="Full research (LightGBM)",
        description="Export five markets then evaluate all default horizons.",
    )
    result = PipelineResult(pipeline_id="full-research-lightgbm")
    csv_dir = data_dir or layout.data
    exp = pipeline_multisource_export(
        data_dir=csv_dir,
        days=export_days,
        solutions_root=solutions_root,
        solution_root=layout.root,
    )
    result.steps.extend(exp.steps)
    ml = pipeline_lightgbm_multisource(
        data_dir=csv_dir,
        all_horizons=True,
        skip_export=True,
        solutions_root=solutions_root,
        results_dir=layout.root,
    )
    result.steps.extend(ml.steps)
    result.outputs = {
        "solution_root": str(layout.root),
        "data_dir": str(csv_dir),
        "runs_dir": str(layout.runs),
        "run_count": ml.outputs.get("run_count"),
        "batch_manifest": ml.outputs.get("batch_manifest"),
    }
    result.write_summary(layout.reports / "pipeline_summary.json")
    return result
