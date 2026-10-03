from __future__ import annotations

import argparse
import json
import sys

from traderbot.market_data import fetch_latest_closed_bar, market_symbol
from traderbot.terminal.events import signal_event_dict
from traderbot.terminal.session import algorithm_from_args, execution_from_args


def run_once(args: argparse.Namespace) -> None:
    symbol = market_symbol(args.src, args.dst)
    bar = fetch_latest_closed_bar(symbol=symbol, resolution=args.interval)
    if bar is None:
        print("no candle data from UDF", file=sys.stderr)
        raise SystemExit(1)

    algo = algorithm_from_args(args)
    algo.reset()
    action = algo.on_bar(bar)
    execution = execution_from_args(args)
    mode = execution.mode

    permitted = execution.permits(action)
    payload = signal_event_dict(
        action,
        bar,
        mode=mode,
        strategy_id=args.strategy,
        event="once",
    )
    payload["permitted"] = permitted
    print(json.dumps(payload, ensure_ascii=False))
