from __future__ import annotations

import argparse

from traderbot.algorithms.base import Algorithm
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.traders.execution import ExecutionPolicy


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
