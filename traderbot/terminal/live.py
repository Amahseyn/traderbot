from __future__ import annotations

import argparse
import sys

from traderbot.bots.base import Bot
from traderbot.market_data import incremental_bar_source, market_symbol
from traderbot.terminal.session import build_terminal_trader


def run_live(args: argparse.Namespace) -> None:
    symbol = market_symbol(args.src, args.dst)
    trader = build_terminal_trader(
        args,
        bar_source=incremental_bar_source(symbol=symbol, resolution=args.interval),
    )

    if args.live:
        print(
            "live mode: default on_signal is a no-op; subclass AlgorithmTrader for real orders",
            file=sys.stderr,
        )

    bot = Bot([trader], interval_sec=args.poll_sec)
    try:
        bot.run(max_steps=args.max_steps)
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
