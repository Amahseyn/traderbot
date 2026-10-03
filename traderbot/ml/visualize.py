from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from traderbot.ml.results import ModelRunResult

from traderbot.ml.metrics import DEFAULT_SAMPLE_USD, format_metrics_block


def _annotate_metrics(ax, metrics: dict[str, float]) -> None:
    ax.text(
        0.02,
        0.98,
        format_metrics_block(metrics),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=9,
        family="monospace",
        bbox={"boxstyle": "round", "facecolor": "white", "edgecolor": "#cccccc", "alpha": 0.92},
    )


@dataclass(frozen=True, slots=True)
class VisualizationPaths:
    actual_vs_predicted: Path
    residuals: Path
    sample_equity: Path | None = None
    feature_importance: Path | None = None


def render_result_plots(result: ModelRunResult, out_dir: Path) -> VisualizationPaths:
    """
    Write PNG charts for a :class:`ModelRunResult`.

    Requires optional ``matplotlib`` (``pip install -e ".[viz]"``).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plots_dir = out_dir if out_dir.name == "visualizations" else out_dir / "visualizations"
    plots_dir.mkdir(parents=True, exist_ok=True)
    avp = plots_dir / "actual_vs_predicted.png"
    res_path = plots_dir / "residuals.png"

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(result.y_true, label="actual", linewidth=1.2)
    ax.plot(result.y_pred, label="predicted", linewidth=1.2, alpha=0.85)
    ax.set_title(f"{result.model_id} — forward return ({result.horizon_label})")
    ax.set_xlabel("holdout index")
    ax.set_ylabel("log return")
    ax.legend(loc="best")
    _annotate_metrics(ax, result.metrics)
    fig.tight_layout()
    fig.savefig(avp, dpi=120)
    plt.close(fig)

    residuals = [t - p for t, p in zip(result.y_true, result.y_pred, strict=True)]
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.bar(range(len(residuals)), residuals, width=1.0, color="#4c72b0", alpha=0.7)
    ax.axhline(0.0, color="black", linewidth=0.8)
    ax.set_title("Residuals (actual − predicted)")
    _annotate_metrics(ax, result.metrics)
    fig.tight_layout()
    fig.savefig(res_path, dpi=120)
    plt.close(fig)

    sample_path: Path | None = None
    init = float(result.metrics.get("initial_usd", DEFAULT_SAMPLE_USD))
    strat_curve = result.extra.get("strategy_equity")
    bh_curve = result.extra.get("buy_hold_equity")
    if not strat_curve or not bh_curve:
        from traderbot.ml.simulator import simulate_holdout_account

        sim = simulate_holdout_account(
            result.y_true,
            result.y_pred,
            result.timestamps,
            horizon_bars=result.horizon_bars,
            bar_minutes=result.bar_minutes,
            price_series=result.price_series,
            initial_usd=init,
            sim_config=result.simulation_config,
        )
        strat_curve, bh_curve = sim.strategy_equity, sim.buy_hold_equity
    sample_path = plots_dir / "sample_100_usd.png"
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(strat_curve, label=f"Strategy (from ${init:.0f})", linewidth=1.4, color="#2ca02c")
    ax.plot(bh_curve, label=f"Buy & hold (from ${init:.0f})", linewidth=1.2, color="#ff7f0e", alpha=0.9)
    ax.set_title(f"Paper account — ${init:.0f} start ({result.horizon_label} signals)")
    ax.set_xlabel("holdout step")
    ax.set_ylabel("USD")
    ax.legend(loc="best")
    ax.axhline(init, color="#888888", linewidth=0.8, linestyle="--")
    _annotate_metrics(ax, result.metrics)
    fig.tight_layout()
    fig.savefig(sample_path, dpi=120)
    plt.close(fig)

    fi_path: Path | None = None
    importance = result.extra.get("feature_importance")
    if isinstance(importance, dict) and importance:
        fi_path = plots_dir / "feature_importance.png"
        names = list(importance.keys())
        values = [importance[k] for k in names]
        fig, ax = plt.subplots(figsize=(7, max(3, len(names) * 0.25)))
        ax.barh(names, values, color="#55a868")
        ax.set_title("Feature importance (gain)")
        _annotate_metrics(ax, result.metrics)
        fig.tight_layout()
        fig.savefig(fi_path, dpi=120)
        plt.close(fig)

    return VisualizationPaths(
        actual_vs_predicted=avp,
        residuals=res_path,
        sample_equity=sample_path,
        feature_importance=fi_path,
    )
