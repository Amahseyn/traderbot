from __future__ import annotations

import argparse
import sys
import time

from traderbot.backtesting import load_bars_csv
from traderbot.terminal.events import print_signal_event
from traderbot.terminal.utils import algorithm_from_args, execution_from_args


def run_replay(args: argparse.Namespace) -> None:
    bars = load_bars_csv(args.csv)
    if not bars:
        print("No bars in CSV", file=sys.stderr)
        raise SystemExit(1)
    if args.max_bars is not None:
        bars = bars[-args.max_bars :]

    algo = algorithm_from_args(args)
    algo.reset()
    execution = execution_from_args(args)
    mode = execution.mode

    for bar in bars:
        action = algo.on_bar(bar)
        if execution.permits(action):
            print_signal_event(
                action,
                bar,
                mode=mode,
                strategy_id=args.strategy,
                emit_holds=args.emit_holds,
            )
        elif args.emit_holds and action == "hold":
            print_signal_event(
                action,
                bar,
                mode=mode,
                strategy_id=args.strategy,
                emit_holds=True,
            )
        if args.pace_sec > 0:
            time.sleep(args.pace_sec)
