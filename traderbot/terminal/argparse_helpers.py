from __future__ import annotations

import argparse

from traderbot.algorithms.cli_args import add_strategy_param_flags
from traderbot.algorithms.registry import implemented_strategy_ids
from traderbot.markets.market_data import RESOLUTIONS
from traderbot.terminal.namespace_keys import EMIT_HOLDS, LIVE, NO_BUY, NO_SELL


def add_market_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--src", default="btc", help="Base asset (e.g. btc)")
    parser.add_argument("--dst", default="rls", help="Quote asset (rls/irt or usdt)")
    parser.add_argument(
        "--interval",
        default="60",
        choices=RESOLUTIONS,
        help="Candle resolution (Nobitex UDF)",
    )


def add_strategy_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--strategy", choices=implemented_strategy_ids(), default="sma_cross")
    add_strategy_param_flags(parser)


def add_loop_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--poll-sec",
        type=float,
        default=60.0,
        help="Seconds between loop iterations (live run only)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Stop after N loop iterations (default: run until Ctrl+C)",
    )


def add_execution_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--live",
        action="store_true",
        dest=LIVE,
        help="Use live execution policy (override on_signal for real orders)",
    )
    parser.add_argument("--no-buy", action="store_true", dest=NO_BUY, help="Ignore buy signals")
    parser.add_argument("--no-sell", action="store_true", dest=NO_SELL, help="Ignore sell signals")
    parser.add_argument(
        "--emit-holds",
        action="store_true",
        dest=EMIT_HOLDS,
        help="Print JSON lines for hold actions as well as buy/sell",
    )
