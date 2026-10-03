from __future__ import annotations

import argparse
import sys

from traderbot.algorithms.base import Algorithm
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.client import NobitexClient, NobitexClientError
from traderbot.terminal.trader import TerminalAlgorithmTrader
from traderbot.traders.execution import ExecutionPolicy
from traderbot.traders.strategies.algorithm_trader import BarSource


def execution_from_args(args: argparse.Namespace) -> ExecutionPolicy:
    allow_buy = not getattr(args, "no_buy", False)
    allow_sell = not getattr(args, "no_sell", False)
    if getattr(args, "live", False):
        return ExecutionPolicy.live(allow_buy=allow_buy, allow_sell=allow_sell)
    return ExecutionPolicy(mode="paper", allow_buy=allow_buy, allow_sell=allow_sell)


def algorithm_from_args(args: argparse.Namespace) -> Algorithm:
    return algorithm_for_id(
        args.strategy,
        **strategy_kwargs_from_namespace(args.strategy, args),
    )


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
    trader.emit_holds = getattr(args, "emit_holds", False)
    return trader
