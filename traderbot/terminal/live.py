from __future__ import annotations

import argparse
import sys

from traderbot.bots.base import Bot
from traderbot.terminal.namespace_keys import LIVE
from traderbot.terminal.session import build_terminal_trader


def run_live(args: argparse.Namespace) -> None:
    trader = build_terminal_trader(args, bar_source=None)

    if getattr(args, LIVE, False):
        print(
            "live mode: market orders via Nobitex API; use --no-buy/--no-sell to gate sides",
            file=sys.stderr,
        )

    should_stop = getattr(args, "should_stop", None)
    bot = Bot([trader], interval_sec=args.poll_sec)
    try:
        bot.run(max_steps=args.max_steps, should_stop=should_stop)
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)
