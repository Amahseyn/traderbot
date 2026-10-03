from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from traderbot.pipelines.registry import list_pipelines, run_pipeline
from traderbot.solutions.layout import SOLUTIONS_ROOT, solution_slug


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run named end-to-end traderbot pipelines.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="List available pipelines")

    run = sub.add_parser("run", help="Execute a pipeline")
    run.add_argument("pipeline_id", help="e.g. full-research-lightgbm")
    run.add_argument("--data-dir", type=Path, default=None, help="Override CSV input directory")
    run.add_argument(
        "--solution-root",
        type=Path,
        default=None,
        help="Override solutions/<slug>/ root (default: solutions/<pipeline_slug>/)",
    )
    run.add_argument("--solutions-root", type=Path, default=SOLUTIONS_ROOT, help="Parent of all solutions")
    run.add_argument("--csv", type=Path, help="Required for single-asset pipelines")
    run.add_argument("--skip-export", action="store_true")
    run.add_argument("--export-days", type=int, default=90)
    run.add_argument("--fast", type=int, default=5, help="SMA fast period")
    run.add_argument("--slow", type=int, default=20, help="SMA slow period")
    run.add_argument("--horizon-bars", type=int, default=4)
    run.add_argument("--bar-minutes", type=int, default=60)

    args = parser.parse_args(argv)

    if args.command == "list":
        rows = [
            {
                "id": p.id,
                "title": p.title,
                "description": p.description,
                "solution_dir": str(args.solutions_root / solution_slug(p.id)),
            }
            for p in list_pipelines()
        ]
        print(json.dumps(rows, indent=2))
        return

    kwargs: dict = {
        "solutions_root": args.solutions_root,
        "results_dir": args.solution_root,
    }
    pid = args.pipeline_id

    if pid in ("lightgbm-single-asset", "chronos-single", "sma-backtest"):
        if args.csv is None:
            print("--csv is required for this pipeline", file=sys.stderr)
            sys.exit(2)
        kwargs["csv_path"] = args.csv

    if pid in (
        "multisource-export",
        "lightgbm-multisource-default",
        "lightgbm-multisource-all-horizons",
        "full-research-lightgbm",
    ):
        if args.data_dir is not None:
            kwargs["data_dir"] = args.data_dir

    if pid.startswith("lightgbm-multisource"):
        kwargs["skip_export"] = args.skip_export

    if pid == "full-research-lightgbm":
        kwargs["export_days"] = args.export_days

    if pid == "chronos-single":
        kwargs["horizon_bars"] = args.horizon_bars
        kwargs["bar_minutes"] = args.bar_minutes

    if pid == "sma-backtest":
        kwargs["fast"] = args.fast
        kwargs["slow"] = args.slow

    if pid == "multisource-export":
        kwargs["days"] = args.export_days
        kwargs.pop("skip_export", None)

    try:
        result = run_pipeline(pid, **kwargs)
    except KeyError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    print(
        json.dumps(
            {
                "pipeline_id": result.pipeline_id,
                "solution_root": result.outputs.get("solution_root"),
                "steps": [s.__dict__ for s in result.steps],
                "outputs": result.outputs,
            },
            indent=2,
        )
    )
