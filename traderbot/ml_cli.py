from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from traderbot.backtest import load_bars_csv
from traderbot.ml.batch import run_batch_on_directory
from traderbot.ml.pipeline import model_for_id, run_forecast_eval
from traderbot.ml.registry import list_models
from traderbot.ml.results import save_run_result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Evaluate crypto time-series forecast models.")
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="List reference models for crypto forecasting")
    catalog.add_argument("--implemented", action="store_true")
    catalog.add_argument("--implemented-only", action="store_true", dest="implemented")

    run = sub.add_parser("run", help="Train/eval on OHLC CSV and write results + plots")
    run.add_argument("csv", type=Path)
    run.add_argument("--model", choices=("lightgbm", "chronos"), default="lightgbm")
    run.add_argument("--horizon-bars", type=int, default=4, help="e.g. 4 on 1h bars = 4h ahead")
    run.add_argument("--bar-minutes", type=int, default=60)
    run.add_argument("--out", type=Path, default=Path("results"))
    run.add_argument("--train-ratio", type=float, default=0.8)

    batch = sub.add_parser("batch", help="Run model on every CSV in a directory; write plots per dataset")
    batch.add_argument("csv_dir", type=Path)
    batch.add_argument("--model", choices=("lightgbm", "chronos"), default="lightgbm")
    batch.add_argument("--out", type=Path, default=Path("results"))
    batch.add_argument("--train-ratio", type=float, default=0.8)
    batch.add_argument("--min-bars", type=int, default=50)
    batch.add_argument("--no-plots", action="store_true")
    batch.add_argument(
        "--all-horizons",
        action="store_true",
        help="Run every default horizon (1m,5m,1h,2h,4h,6h,12h,1d) that fits each CSV",
    )

    args = parser.parse_args(argv)

    if args.command == "catalog":
        entries = list_models(implemented_only=args.implemented)
        print(json.dumps([asdict(e) for e in entries], indent=2))
        return

    if args.command == "batch":
        results = run_batch_on_directory(
            args.csv_dir,
            out_dir=args.out,
            model_id=args.model,
            min_bars=args.min_bars,
            train_ratio=args.train_ratio,
            render_plots=not args.no_plots,
            all_horizons=args.all_horizons,
        )
        print(
            json.dumps(
                {
                    "run_count": len(results),
                    "out_dir": str(args.out),
                    "manifest": str(args.out / "batch_manifest.json"),
                },
                indent=2,
            )
        )
        return

    bars = load_bars_csv(args.csv)
    if len(bars) < 50:
        print("need at least ~50 bars for indicators + holdout", file=sys.stderr)
        sys.exit(1)
    model = model_for_id(args.model)
    result = run_forecast_eval(
        bars,
        model,
        horizon_bars=args.horizon_bars,
        bar_minutes=args.bar_minutes,
        train_ratio=args.train_ratio,
    )
    out = args.out / f"{args.model}_{result.horizon_label}"
    save_run_result(result, out)
    print(json.dumps(result.to_dict(), indent=2))
    if result.visualization:
        print(f"plots: {result.visualization.actual_vs_predicted.parent}", file=sys.stderr)
