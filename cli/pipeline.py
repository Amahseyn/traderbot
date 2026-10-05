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

    list_cmd = sub.add_parser("list", help="List available pipelines")
    list_cmd.add_argument("--solutions-root", type=Path, default=SOLUTIONS_ROOT, help="Parent of all solutions")

    run_config = sub.add_parser(
        "run-config",
        help="Run a pipeline from an experiment JSON (status: pending → running → completed)",
    )
    run_config.add_argument(
        "config",
        type=Path,
        help="e.g. config/experiment.crypto-1h-local.json",
    )
    run_config.add_argument(
        "--force",
        action="store_true",
        help="Re-run even when status is completed",
    )
    run_config.add_argument("--dry-run", action="store_true", help="Print resolved kwargs only")
    run_config.add_argument(
        "--step",
        dest="step_id",
        default=None,
        help="Run a single test_steps step_id from the config",
    )

    run = sub.add_parser("run", help="Execute a pipeline")
    run.add_argument("pipeline_id", help="e.g. crypto-1h-local")
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
    run.add_argument(
        "--tail-bars",
        type=int,
        default=None,
        help="For crypto-1h-local: use only the last N 1h candles (default: entire CSV).",
    )
    run.add_argument(
        "--holdout-tail-bars",
        type=int,
        default=None,
        help="For crypto-1h-local: rank strategies on the last N bars (holdout_return_pct).",
    )
    run.add_argument(
        "--symbol",
        default=None,
        help="Nobitex symbol for 1h CSV (e.g. BTCIRT, ETHUSDT); ignored when --csv is set.",
    )
    run.add_argument(
        "--all-assets",
        action="store_true",
        help="Run every *_60.csv under crypto OHLC (no download).",
    )

    args = parser.parse_args(argv)

    if args.command == "run-config":
        from traderbot.pipelines.experiment_config import run_experiment_config

        payload = run_experiment_config(
            args.config,
            force=args.force,
            dry_run=args.dry_run,
            step_id=args.step_id,
        )
        print(json.dumps(payload, indent=2, default=str))
        return

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

    if pid == "sma-backtest":
        if args.csv is None:
            print("--csv is required for this pipeline", file=sys.stderr)
            sys.exit(2)
        kwargs["csv_path"] = args.csv

    if pid == "crypto-1h-local":
        if args.csv is not None:
            kwargs["csv_path"] = args.csv
        if args.symbol is not None:
            kwargs["symbol"] = args.symbol
        if args.all_assets:
            kwargs["all_assets"] = True
        if args.tail_bars is not None:
            kwargs["tail_bars"] = args.tail_bars
        if args.holdout_tail_bars is not None:
            kwargs["holdout_tail_bars"] = args.holdout_tail_bars

    if pid == "multisource-export":
        if args.data_dir is not None:
            kwargs["data_dir"] = args.data_dir

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
