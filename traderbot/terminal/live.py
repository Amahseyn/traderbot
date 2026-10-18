from __future__ import annotations

import argparse
import sys

from traderbot.bots.base import Bot
from traderbot.terminal.namespace_keys import LIVE
from traderbot.terminal.session import build_terminal_trader


def run_live(args: argparse.Namespace) -> None:
    trader = build_terminal_trader(args, bar_source=None)

    if getattr(args, LIVE, False):
        exchange = getattr(args, "exchange", "hyperliquid")
        print(
            f"live mode: market orders via {exchange}; use --no-buy/--no-sell to gate sides",
            file=sys.stderr,
        )

    should_stop = getattr(args, "should_stop", None)
    bar_seconds = None
    if getattr(args, "align_to_bar", False):
        from traderbot.markets.utils import resolution_seconds

        try:
            bar_seconds = resolution_seconds(str(args.interval))
        except (KeyError, ValueError, TypeError):
            bar_seconds = None
    bot = Bot([trader], interval_sec=args.poll_sec, bar_seconds=bar_seconds)
    try:
        bot.run(max_steps=args.max_steps, should_stop=should_stop)
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
