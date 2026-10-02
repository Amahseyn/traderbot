from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SOLUTIONS_ROOT = Path("solutions")


def solution_slug(pipeline_id: str) -> str:
    """``lightgbm-multisource-all-horizons`` → ``lightgbm_multisource_all_horizons``."""
    return pipeline_id.replace("-", "_")


@dataclass
class SolutionLayout:
    """
    One solution = one pipeline output tree::

        solutions/<slug>/
          README.md
          data/              # exported OHLC CSVs (when applicable)
          runs/<asset>/<horizon>/
            results.json
            visualizations/*.png
          reports/
            pipeline_summary.json
            batch_manifest.json
    """

    pipeline_id: str
    root: Path
    data: Path
    runs: Path
    reports: Path

    @property
    def slug(self) -> str:
        return solution_slug(self.pipeline_id)

    def ensure(self) -> SolutionLayout:
        for path in (self.root, self.data, self.runs, self.reports):
            path.mkdir(parents=True, exist_ok=True)
        return self

    def run_dir(self, dataset_stem: str, horizon_label: str) -> Path:
        path = self.runs / dataset_stem / horizon_label
        path.mkdir(parents=True, exist_ok=True)
        return path

    def run_dir_flat(self, run_name: str) -> Path:
        """Single-level run folder (e.g. SMA backtest)."""
        path = self.runs / run_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def visualizations_dir(self, run_dir: Path) -> Path:
        path = run_dir / "visualizations"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def write_readme(self, *, title: str, description: str) -> Path:
        readme = self.root / "README.md"
        readme.write_text(
            f"# {title}\n\n"
            f"**Solution id:** `{self.pipeline_id}`  \n"
            f"**Folder:** `{self.root}`\n\n"
            f"{description}\n\n"
            "## Layout\n\n"
            "- `data/` — market CSV inputs\n"
            "- `runs/<symbol_interval>/<horizon>/` — model metrics + `visualizations/`\n"
            "- `reports/` — `pipeline_summary.json`, manifests\n",
            encoding="utf-8",
        )
        return readme

    def write_meta(self) -> Path:
        meta_path = self.reports / "solution_meta.json"
        payload = {
            "pipeline_id": self.pipeline_id,
            "slug": self.slug,
            "root": str(self.root),
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return meta_path


def prepare_solution(
    pipeline_id: str,
    *,
    solutions_root: Path = SOLUTIONS_ROOT,
    solution_root: Path | None = None,
    title: str | None = None,
    description: str = "",
) -> SolutionLayout:
    slug = solution_slug(pipeline_id)
    root = solution_root if solution_root is not None else solutions_root / slug
    layout = SolutionLayout(
        pipeline_id=pipeline_id,
        root=root,
        data=root / "data",
        runs=root / "runs",
        reports=root / "reports",
    ).ensure()
    layout.write_readme(
        title=title or pipeline_id,
        description=description or "Traderbot pipeline solution output.",
    )
    layout.write_meta()
    return layout
