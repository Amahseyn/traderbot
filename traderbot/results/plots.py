from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

_MANIFEST_NAMES = (
    "compare_manifest.json",
    "batch_manifest.json",
    "backtest_summary.json",
    "results.json",
    "live_markets_manifest.json",
    "pipeline_summary.json",
)


def _collect_png_strings(obj: Any, acc: list[Path]) -> None:
    if isinstance(obj, dict):
        if "visualization" in obj:
            _collect_png_strings(obj["visualization"], acc)
        for value in obj.values():
            _collect_png_strings(value, acc)
    elif isinstance(obj, list):
        for item in obj:
            _collect_png_strings(item, acc)
    elif isinstance(obj, str) and obj.lower().endswith(".png"):
        path = Path(obj)
        if path.is_file():
            acc.append(path.resolve())


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(path.resolve())
    return out


def discover_result_plots(root: Path) -> list[Path]:
    root = root.expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(root)
    if root.is_file():
        if root.suffix.lower() == ".png":
            return [root]
        raise FileNotFoundError(f"not a PNG or results directory: {root}")

    plots: list[Path] = []
    if root.name == "visualizations":
        plots.extend(sorted(root.glob("*.png")))
    elif (root / "visualizations").is_dir():
        plots.extend(sorted((root / "visualizations").glob("*.png")))

    for name in _MANIFEST_NAMES:
        for manifest in (root / name, root / "reports" / name):
            if manifest.is_file():
                _collect_png_strings(json.loads(manifest.read_text(encoding="utf-8")), plots)

    for viz_dir in root.rglob("visualizations"):
        if viz_dir.is_dir():
            plots.extend(sorted(viz_dir.glob("*.png")))

    return _dedupe_paths(plots)


def results_plots_catalog(root: Path) -> dict[str, Any]:
    plots = discover_result_plots(root)
    return {
        "root": str(root.expanduser().resolve()),
        "plot_count": len(plots),
        "plots": [str(p) for p in plots],
    }


def open_plots_in_viewer(paths: Sequence[Path]) -> None:
    if not paths:
        return
    if sys.platform == "darwin":
        opener = ["open"]
    elif shutil.which("xdg-open"):
        opener = ["xdg-open"]
    else:
        raise RuntimeError("no system image viewer (macOS open or xdg-open)")
    for path in paths:
        subprocess.run([*opener, str(path)], check=False)


def show_plots_interactive(paths: Sequence[Path]) -> None:
    import matplotlib.pyplot as plt

    for path in paths:
        image = plt.imread(path)
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.imshow(image)
        ax.axis("off")
        ax.set_title(path.name)
        fig.tight_layout()
    plt.show()
