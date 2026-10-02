from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from traderbot.ml.metrics import DEFAULT_SAMPLE_USD, format_metrics_line, full_metrics
from traderbot.ml.visualize import VisualizationPaths, render_result_plots


@dataclass
class ModelRunResult:
    """Holdout evaluation for one model and forecast horizon."""

    model_id: str
    horizon_label: str
    horizon_bars: int
    feature_names: list[str]
    timestamps: list[int]
    y_true: list[float]
    y_pred: list[float]
    sample_usd: float = DEFAULT_SAMPLE_USD
    bar_minutes: int = 60
    price_series: list[tuple[int, float]] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    visualization: VisualizationPaths | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.metrics:
            from traderbot.ml.simulator import simulate_holdout_account

            sim = simulate_holdout_account(
                self.y_true,
                self.y_pred,
                self.timestamps,
                horizon_bars=self.horizon_bars,
                bar_minutes=self.bar_minutes,
                price_series=self.price_series,
                initial_usd=self.sample_usd,
            )
            self.extra.setdefault("strategy_equity", sim.strategy_equity)
            self.extra.setdefault("buy_hold_equity", sim.buy_hold_equity)
            self.metrics = full_metrics(
                self.y_true,
                self.y_pred,
                initial_usd=self.sample_usd,
                simulation=sim,
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "horizon_label": self.horizon_label,
            "horizon_bars": self.horizon_bars,
            "metrics": self.metrics,
            "feature_names": self.feature_names,
            "n_samples": len(self.y_true),
            "extra": self.extra,
            "visualization": (
                None
                if self.visualization is None
                else {
                    "actual_vs_predicted": str(self.visualization.actual_vs_predicted),
                    "residuals": str(self.visualization.residuals),
                    "feature_importance": (
                        str(self.visualization.feature_importance) if self.visualization.feature_importance else None
                    ),
                    "sample_equity": (
                        str(self.visualization.sample_equity) if self.visualization.sample_equity else None
                    ),
                }
            ),
        }


def save_run_result(result: ModelRunResult, out_dir: Path, *, render_plots: bool = True) -> ModelRunResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    if render_plots:
        result.visualization = render_result_plots(result, out_dir)
        label = result.extra.get("dataset") or f"{result.model_id}_{result.horizon_label}"
        print(
            format_metrics_line(result.metrics, prefix=f"{label}: "),
            file=sys.stderr,
        )
    summary_path = out_dir / "results.json"
    summary_path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
    return result
