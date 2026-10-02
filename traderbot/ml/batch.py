from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from traderbot.backtest import load_bars_csv
from traderbot.data.crypto_store import horizon_label_from_csv_dir
from traderbot.ml.intervals import (
    default_eval_horizon,
    forecast_horizons_for_resolution,
    min_bars_for_forecast_eval,
    resolution_from_csv_path,
    resolution_minutes,
)
from traderbot.ml.pipeline import model_for_id, run_forecast_eval
from traderbot.ml.results import ModelRunResult, save_run_result

if TYPE_CHECKING:
    from traderbot.solutions.layout import SolutionLayout


def _visualization_paths(result: ModelRunResult) -> dict[str, str | None] | None:
    if result.visualization is None:
        return None
    return {
        "actual_vs_predicted": str(result.visualization.actual_vs_predicted),
        "residuals": str(result.visualization.residuals),
        "feature_importance": (
            str(result.visualization.feature_importance) if result.visualization.feature_importance else None
        ),
        "sample_equity": (str(result.visualization.sample_equity) if result.visualization.sample_equity else None),
    }


def run_batch_on_directory(
    csv_dir: Path,
    *,
    out_dir: Path | None = None,
    layout: SolutionLayout | None = None,
    model_id: str = "lightgbm",
    min_bars: int = 50,
    train_ratio: float = 0.8,
    render_plots: bool = True,
    all_horizons: bool = False,
    **model_kwargs: Any,
) -> list[ModelRunResult]:
    """
    Evaluate each ``*.csv`` in ``csv_dir``.

    With ``layout``: writes under ``solutions/<slug>/runs/<asset>/<horizon>/``.
    Otherwise uses ``out_dir`` (legacy flat folders).
    """
    csv_dir = csv_dir.resolve()
    if layout is None and out_dir is None:
        raise ValueError("provide out_dir or layout")
    if layout is not None:
        layout.ensure()
    elif out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)

    model = model_for_id(model_id, **model_kwargs)
    results: list[ModelRunResult] = []
    runs_meta: list[dict[str, Any]] = []

    fixed_horizon = horizon_label_from_csv_dir(csv_dir)

    for csv_path in sorted(csv_dir.glob("*.csv")):
        bars = load_bars_csv(csv_path)
        resolution = resolution_from_csv_path(csv_path.name)
        bar_minutes = resolution_minutes(resolution)
        if fixed_horizon:
            horizon_specs = [
                (hb, lbl) for hb, lbl in forecast_horizons_for_resolution(resolution) if lbl == fixed_horizon
            ]
        elif all_horizons:
            horizon_specs = forecast_horizons_for_resolution(resolution)
        else:
            horizon_bars_default, _ = default_eval_horizon(resolution)
            horizon_specs = [(horizon_bars_default, "")]

        for horizon_bars, _label in horizon_specs:
            need = min_bars_for_forecast_eval(horizon_bars) if all_horizons else min_bars
            if len(bars) < need:
                continue
            result = run_forecast_eval(
                bars,
                model,
                horizon_bars=horizon_bars,
                bar_minutes=bar_minutes,
                train_ratio=train_ratio,
            )
            result.extra["dataset"] = csv_path.stem
            if layout is not None:
                run_out = layout.run_dir(csv_path.stem, result.horizon_label)
            elif all_horizons:
                run_out = out_dir / f"{csv_path.stem}_{result.horizon_label}"  # type: ignore[operator]
            else:
                run_out = out_dir / csv_path.stem  # type: ignore[operator]
            save_run_result(result, run_out, render_plots=render_plots)
            results.append(result)
            runs_meta.append(
                {
                    "dataset": csv_path.stem,
                    "horizon_label": result.horizon_label,
                    "horizon_bars": result.horizon_bars,
                    "metrics": result.metrics,
                    "out_dir": str(run_out),
                    "visualization": _visualization_paths(result),
                }
            )

    manifest = {
        "model_id": model_id,
        "csv_dir": str(csv_dir),
        "all_horizons": all_horizons,
        "run_count": len(results),
        "runs": runs_meta,
    }
    if layout is not None:
        manifest["solution"] = layout.slug
        manifest_path = layout.reports / "batch_manifest.json"
    else:
        manifest_path = out_dir / "batch_manifest.json"  # type: ignore[operator]
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return results
