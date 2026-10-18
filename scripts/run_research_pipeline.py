#!/usr/bin/env python3
"""Run single-market or full-universe research (export → Optuna → compare)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Traderbot market research pipelines")
    sub = parser.add_subparsers(dest="command", required=True)

    single = sub.add_parser("single", help="One symbol, multiple intervals")
    single.add_argument("--symbol", default="BTCUSDT", help="Market symbol, e.g. ARBUSDT")
    single.add_argument(
        "--intervals",
        default="1,5,15,60",
        help="Comma-separated Hyperliquid resolutions",
    )
    single.add_argument("--export-days", type=int, default=30)
    single.add_argument("--exchange", default="hyperliquid", choices=("hyperliquid", "nobitex"))
    single.add_argument("--optimize-n-trials", type=int, default=80)
    single.add_argument("--out", type=Path, default=None, help="Solution root under solutions/")

    universe = sub.add_parser("universe", help="Many markets × intervals × all strategies")
    universe.add_argument("--intervals", default="1,5,15,60")
    universe.add_argument("--export-days", type=int, default=30)
    universe.add_argument("--exchange", default="hyperliquid", choices=("hyperliquid", "nobitex"))
    universe.add_argument(
        "--top-markets",
        type=int,
        default=30,
        help="Cap market count (Hyperliquid universe or jobs file)",
    )
    universe.add_argument("--jobs-file", type=Path, default=None, help="Nobitex export jobs JSON")
    universe.add_argument("--optimize-n-trials", type=int, default=80)
    universe.add_argument("--out", type=Path, default=None)

    body = sub.add_parser("print-body", help="Emit JSON body for POST /api/jobs/custom-research")
    body.add_argument("mode", choices=("single", "universe"))
    body.add_argument("--symbol", default="BTCUSDT")
    body.add_argument("--intervals", default="1,5,15,60")
    body.add_argument("--top-markets", type=int, default=30)
    body.add_argument("--export-days", type=int, default=30)
    body.add_argument("--optimize-n-trials", type=int, default=80)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    if args.command == "print-body":
        from traderbot.pipelines.market_research import (
            build_full_universe_research_body,
            build_single_market_research_body,
        )

        if args.mode == "single":
            payload = build_single_market_research_body(
                market_symbol=args.symbol,
                intervals=[p.strip() for p in args.intervals.split(",") if p.strip()],
                export_days=args.export_days,
                optimize_n_trials=args.optimize_n_trials,
            )
        else:
            payload = build_full_universe_research_body(
                intervals=[p.strip() for p in args.intervals.split(",") if p.strip()],
                export_days=args.export_days,
                top_markets=args.top_markets,
                optimize_n_trials=args.optimize_n_trials,
            )
        print(json.dumps(payload, indent=2))
        return 0

    from traderbot.pipelines.market_research import (
        pipeline_full_universe_research,
        pipeline_single_market_research,
    )

    if args.command == "single":
        result = pipeline_single_market_research(
            market_symbol=args.symbol,
            intervals=args.intervals,
            export_days=args.export_days,
            exchange=args.exchange,
            optimize_n_trials=args.optimize_n_trials,
            solution_root=args.out,
        )
    else:
        result = pipeline_full_universe_research(
            intervals=args.intervals,
            export_days=args.export_days,
            exchange=args.exchange,
            jobs_file=args.jobs_file,
            top_markets=args.top_markets,
            optimize_n_trials=args.optimize_n_trials,
            solution_root=args.out,
        )
    print(json.dumps(result.outputs, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
