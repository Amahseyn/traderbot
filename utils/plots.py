from __future__ import annotations

import math
from pathlib import Path


def visualizations_dir(out_dir: Path) -> Path:
    path = out_dir if out_dir.name == "visualizations" else out_dir / "visualizations"
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_subplot_grid_shape(panel_count: int, *, max_columns: int = 3) -> tuple[int, int]:
    column_count = min(max_columns, max(1, math.ceil(math.sqrt(panel_count))))
    row_count = math.ceil(panel_count / column_count) if panel_count else 1
    return row_count, column_count


def hide_unused_subplot_axes(axes, *, used_count: int, row_count: int, column_count: int) -> None:
    for panel_index in range(used_count, row_count * column_count):
        axes[panel_index // column_count][panel_index % column_count].set_visible(False)


def configure_matplotlib(*, interactive: bool = False) -> None:
    import matplotlib

    if not interactive:
        matplotlib.use("Agg")
