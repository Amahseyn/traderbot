from __future__ import annotations

import argparse

from traderbot.algorithms.base import Algorithm
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.algorithms.cli_args import merge_strategy_namespace
from traderbot.algorithms.optimized_params import resolve_optimized_namespace
from traderbot.markets.market_data import market_symbol
from traderbot.terminal.namespace_keys import LIVE, NO_BUY, NO_SELL
from traderbot.traders.execution import ExecutionPolicy


def execution_from_args(args: argparse.Namespace) -> ExecutionPolicy:
    allow_buy = not getattr(args, NO_BUY, False)
    allow_sell = not getattr(args, NO_SELL, False)
    if getattr(args, LIVE, False):
        return ExecutionPolicy.live(allow_buy=allow_buy, allow_sell=allow_sell)
    return ExecutionPolicy(mode="paper", allow_buy=allow_buy, allow_sell=allow_sell)


def algorithm_from_args(args: argparse.Namespace) -> Algorithm:
    use_optimized = getattr(args, "use_optimized_defaults", False)
    apply_sweep = getattr(args, "apply_sweep_winner", False)
    if use_optimized or apply_sweep:
        src = getattr(args, "src", None)
        dst = getattr(args, "dst", None)
        symbol = market_symbol(str(src), str(dst)) if src and dst else None
        csv_path = getattr(args, "csv", None)
        namespace = resolve_optimized_namespace(
            args.strategy,
            args,
            csv_path=csv_path,
            symbol=symbol,
            resolution=str(getattr(args, "interval", "") or "") or None,
            apply_sweep_winner=apply_sweep,
        )
    else:
        namespace = merge_strategy_namespace(args)
    return algorithm_for_id(
        args.strategy,
        **strategy_kwargs_from_namespace(args.strategy, namespace),
    )
