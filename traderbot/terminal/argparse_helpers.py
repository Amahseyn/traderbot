from __future__ import annotations

import argparse

from traderbot.algorithms.cli_args import add_strategy_param_flags
from traderbot.algorithms.registry import implemented_strategy_ids
from traderbot.markets.market_data import RESOLUTIONS
from traderbot.terminal.namespace_keys import EMIT_HOLDS, LIVE, NO_BUY, NO_SELL


def add_market_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--src", default="btc", help="Base asset (e.g. btc)")
    parser.add_argument(
        "--dst",
        default="usdt",
        help="Quote asset (usdt for Hyperliquid default; rls/irt for Nobitex)",
    )
    parser.add_argument(
        "--interval",
        default="60",
        choices=RESOLUTIONS,
        help="Candle resolution (exchange-specific set when live)",
    )


def add_strategy_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--strategy", choices=implemented_strategy_ids(), default="sma_cross")
    add_strategy_param_flags(parser)


def add_loop_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--poll-sec",
        type=float,
        default=60.0,
        help="Max seconds between loop iterations (live run only)",
    )
    parser.add_argument(
        "--align-to-bar",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Wake right after each bar close instead of every --poll-sec (default: on)",
    )
    parser.add_argument(
        "--ws",
        action="store_true",
        help="Hyperliquid: stream candles over the public websocket (REST fallback when stale)",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Stop after N loop iterations (default: run until Ctrl+C)",
    )


def add_execution_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--exchange",
        choices=("hyperliquid", "nobitex"),
        default="hyperliquid",
        help="Live data and order venue (default: hyperliquid)",
    )
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
    parser.add_argument(
        "--live-quote-budget",
        type=float,
        default=None,
        dest="live_quote_budget",
        help="Live mode: cap buy spend to this quote amount (omit for full wallet)",
    )
