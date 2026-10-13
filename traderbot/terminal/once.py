from __future__ import annotations

import argparse
import json
import sys

from traderbot.algorithms.registry import strategy_kwargs_from_namespace
from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest
from traderbot.algorithms.warmup import warmup_bar_count
from traderbot.markets.exchange import (
    fetch_live_recent_closed_bars,
    live_market_symbol,
    normalize_live_exchange,
)
from traderbot.markets.market_data import fetch_latest_closed_bar
from traderbot.terminal.events import signal_event_dict
from traderbot.terminal.utils import algorithm_from_args, execution_from_args


def run_once(args: argparse.Namespace) -> None:
    exchange = normalize_live_exchange(getattr(args, "exchange", None))
    symbol = live_market_symbol(exchange, args.src, args.dst)
    if exchange == "hyperliquid":
        history = fetch_live_recent_closed_bars(
            exchange=exchange,
            src=args.src,
            dst=args.dst,
            resolution=args.interval,
            max_bars=1,
        )
        bar = history[-1] if history else None
    else:
        bar = fetch_latest_closed_bar(symbol=symbol, resolution=args.interval)
    if bar is None:
        print("no candle data from exchange", file=sys.stderr)
        raise SystemExit(1)

    namespace = namespace_for_strategy_backtest(args.strategy, args)
    kwargs = strategy_kwargs_from_namespace(args.strategy, namespace)
    warmup_count = warmup_bar_count(args.strategy, kwargs)
    history = fetch_live_recent_closed_bars(
        exchange=exchange,
        src=args.src,
        dst=args.dst,
        resolution=args.interval,
        max_bars=warmup_count + 1,
    )
    warmup_bars = [row for row in history if int(row["timestamp"]) < int(bar["timestamp"])]

    algo = algorithm_from_args(args)
    algo.reset()
    for warmup_bar in warmup_bars:
        algo.on_bar(warmup_bar)
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
    payload["warmup_bars"] = len(warmup_bars)
    payload["exchange"] = exchange
    print(json.dumps(payload, ensure_ascii=False))
