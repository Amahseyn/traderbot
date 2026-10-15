#!/usr/bin/env python3
"""Build docs/strategy-matrix-evaluation.md and charts from matrix_summary.json."""

from __future__ import annotations

import json
from pathlib import Path

SUMMARY_PATH = Path("results/strategy_eval/matrix_summary.json")
DOCS_PATH = Path("docs/strategy-matrix-evaluation.md")
CHART_DIR = Path("results/strategy_eval/charts")


def main() -> None:
    if not SUMMARY_PATH.is_file():
        raise SystemExit(f"Missing {SUMMARY_PATH}; run scripts/run_strategy_matrix_evaluation.py first")

    payload = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    cells = payload.get("cells", {})
    config = payload.get("config", {})

    lines = [
        "# Strategy matrix evaluation (out-of-sample)",
        "",
        f"- Samples per cell: **{config.get('sample_count')}**",
        f"- History: **{config.get('months')}** months",
        f"- Resolutions: {', '.join(config.get('resolutions', []))}",
        "",
        "Method: random chronological windows, 60/40 train/test, hyperparameters fit on train only,",
        "fees/slippage from `execution_costs` per exchange.",
        "",
        "## Results by cell",
        "",
        "| Cell | Samples | Median return % | % profitable | Median Sharpe | Median excess vs B&H % |",
        "|------|---------|-----------------|--------------|---------------|-------------------------|",
    ]

    for key in sorted(cells.keys()):
        aggregate = cells[key].get("aggregate", {})
        lines.append(
            f"| `{key}` | {aggregate.get('sample_count', 0)} | "
            f"{aggregate.get('median_return_pct', '—')} | "
            f"{aggregate.get('pct_profitable_windows', '—')} | "
            f"{aggregate.get('median_sharpe', '—')} | "
            f"{aggregate.get('median_excess_vs_buy_hold_pct', '—')} |"
        )

    selector_path = Path("config/strategy_selector.json")
    if selector_path.is_file():
        selector = json.loads(selector_path.read_text(encoding="utf-8"))
        recommended = sum(1 for row in selector.values() if row.get("recommended"))
        lines.extend(
            [
                "",
                "## Selector",
                "",
                f"Recommended cells: **{recommended}** / {len(selector)}. See `config/strategy_selector.json`.",
            ]
        )

    DOCS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {DOCS_PATH}")

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return

    CHART_DIR.mkdir(parents=True, exist_ok=True)
    by_strategy: dict[str, list[float]] = {}
    for key, cell in cells.items():
        strategy_id = key.split(":")[-1]
        median = cell.get("aggregate", {}).get("median_return_pct")
        if median is not None:
            by_strategy.setdefault(strategy_id, []).append(float(median))
    if by_strategy:
        labels = sorted(by_strategy.keys())
        values = [sum(by_strategy[label]) / len(by_strategy[label]) for label in labels]
        figure, axis = plt.subplots(figsize=(10, 5))
        axis.bar(labels, values)
        axis.set_title("Mean of median OOS returns across cells")
        axis.set_ylabel("Return %")
        axis.tick_params(axis="x", rotation=45)
        figure.tight_layout()
        figure.savefig(CHART_DIR / "mean_median_return_by_strategy.png", dpi=120)
        plt.close(figure)
        print(f"Wrote {CHART_DIR / 'mean_median_return_by_strategy.png'}")


if __name__ == "__main__":
    main()
