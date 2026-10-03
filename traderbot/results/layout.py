from __future__ import annotations

from pathlib import Path

from traderbot.solutions.layout import SolutionLayout, solution_slug

RESULTS_ROOT = Path("results")


def result_tree_at(root: Path, *, run_id: str = "adhoc") -> SolutionLayout:
    root = root.resolve()
    return SolutionLayout(
        pipeline_id=run_id,
        root=root,
        data=root / "data",
        runs=root / "runs",
        reports=root / "reports",
    ).ensure()


def _slug(name: str) -> str:
    return solution_slug(name.replace(" ", "_"))


def default_ml_batch_out(csv_dir: Path) -> Path:
    return RESULTS_ROOT / "ml" / _slug(csv_dir.name or "batch")


def default_ml_run_out(csv: Path) -> Path:
    return RESULTS_ROOT / "ml" / _slug(csv.stem or "run")


def default_strategy_batch_out(strategy_id: str) -> Path:
    return RESULTS_ROOT / "strategies" / "batch" / _slug(strategy_id)


def default_strategy_compare_out(csv: Path) -> Path:
    return RESULTS_ROOT / "strategies" / "compare" / _slug(csv.stem or "compare")


def default_strategy_backtest_out(csv: Path, strategy_id: str) -> Path:
    return RESULTS_ROOT / "strategies" / "backtest" / _slug(f"{csv.stem}_{strategy_id}")


def default_live_markets_out() -> Path:
    return RESULTS_ROOT / "data" / "live"


def manifest_parent_dir(manifest_path: Path) -> Path:
    parent = manifest_path.parent.resolve()
    if parent.name == "reports":
        return parent.parent
    return parent
