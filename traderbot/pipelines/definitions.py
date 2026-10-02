from __future__ import annotations

import json
from pathlib import Path

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.backtest import load_bars_csv, run_backtest
from traderbot.export_csv import load_jobs, run_export
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
    days: int = 30,
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
    all_horizons: bool = False,
    skip_export: bool = True,
    jobs_file: Path = JOBS_FIVE_SOURCES,
    export_days: int = 30,
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
    all_horizons: bool = True,
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
    horizon_bars: int = 4,
    bar_minutes: int = 60,
    solutions_root: Path = SOLUTIONS_ROOT,
) -> PipelineResult:
    """Single asset → Chronos pretrained eval (requires ``.[chronos]``)."""
    from traderbot.ml.dataset import horizon_label

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
    label = horizon_label(bar_minutes, horizon_bars)
    out = layout.run_dir(csv_path.stem, label)
    save_run_result(eval_result, out)
    result.add_step("chronos_eval", artifacts=[out / "results.json", out / "visualizations"])
    result.outputs = {"solution_root": str(layout.root), "run_dir": str(out), "metrics": eval_result.metrics}
    result.write_summary(layout.reports / "pipeline_summary.json")
    return result


def pipeline_sma_backtest(
    *,
    csv_path: Path,
    results_dir: Path | None = None,
    fast: int = 5,
    slow: int = 20,
    strategy_id: str = "sma_cross",
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


def pipeline_full_research(
    *,
    data_dir: Path | None = None,
    results_dir: Path | None = None,
    export_days: int = 90,
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
