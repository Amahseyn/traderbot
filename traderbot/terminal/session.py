from __future__ import annotations

import argparse
import sys

from traderbot.nobitex.client import NobitexClient, NobitexClientError
from traderbot.terminal.namespace_keys import EMIT_HOLDS
from traderbot.terminal.trader import TerminalAlgorithmTrader
from traderbot.terminal.utils import algorithm_from_args, execution_from_args
from traderbot.traders.strategies.algorithm_trader import BarSource


def build_terminal_trader(
    args: argparse.Namespace,
    *,
    bar_source: BarSource | None,
) -> TerminalAlgorithmTrader:
    try:
        client = NobitexClient.from_env()
    except NobitexClientError as e:
        print(e, file=sys.stderr)
        raise SystemExit(1) from e

    algo = algorithm_from_args(args)
    trader = TerminalAlgorithmTrader(
        client,
        algo,
        bar_source=bar_source,
        execution=execution_from_args(args),
    )
    trader.strategy_id = args.strategy
    trader.emit_holds = getattr(args, EMIT_HOLDS, False)
    return trader
