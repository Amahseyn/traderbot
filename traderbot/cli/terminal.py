from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from traderbot.auth.envfile import load_env_file
from traderbot.terminal.argparse_helpers import (
    add_execution_flags,
    add_loop_flags,
    add_market_flags,
    add_strategy_flags,
)
from traderbot.terminal.catalog import catalog_dict
from traderbot.terminal.live import run_live
from traderbot.terminal.once import run_once
from traderbot.terminal.replay import run_replay


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Terminal live/replay execution for rule strategies (paper by default).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="List terminal commands and strategies")
    catalog.add_argument("--implemented", action="store_true")
    catalog.add_argument("--implemented-only", action="store_true", dest="implemented")

    run = sub.add_parser("run", help="Poll UDF for new candles and step the algorithm")
    add_market_flags(run)
    add_strategy_flags(run)
    add_loop_flags(run)
    add_execution_flags(run)

    once = sub.add_parser("once", help="Evaluate on the latest closed candle once")
    add_market_flags(once)
    add_strategy_flags(once)
    add_execution_flags(once)

    replay = sub.add_parser("replay", help="Replay an OHLC CSV bar-by-bar")
    replay.add_argument("csv", type=Path)
    replay.add_argument("--max-bars", type=int, default=None, help="Only use the last N bars")
    replay.add_argument(
        "--pace-sec",
        type=float,
        default=0.0,
        help="Sleep between bars (demo / slow replay)",
    )
    add_strategy_flags(replay)
    add_execution_flags(replay)

    args = parser.parse_args(argv)

    if args.command == "catalog":
        print(json.dumps(catalog_dict(implemented_only=args.implemented), indent=2))
        return

    load_env_file()

    if args.command == "run":
        run_live(args)
        return
    if args.command == "once":
        run_once(args)
        return
    if args.command == "replay":
        run_replay(args)
        return

    print(f"unknown command {args.command!r}", file=sys.stderr)
    raise SystemExit(1)
