from __future__ import annotations

import argparse
import sys

from traderbot.algorithms.registry import strategy_kwargs_from_namespace
from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest
from traderbot.algorithms.warmup import warmup_bar_count
from traderbot.markets.market_data import (
    fetch_closed_bars_after,
    fetch_recent_closed_bars,
    incremental_bar_source,
    market_symbol,
)
from traderbot.risk.runtime import configure_risk_manager
from traderbot.risk.manager import RiskLimits
from traderbot.nobitex.client import NobitexClient, NobitexClientError
from traderbot.terminal.events import print_tick_event
from traderbot.terminal.namespace_keys import EMIT_HOLDS
from traderbot.terminal.paper_portfolio import PaperPortfolio, default_paper_initial_cash
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

    symbol = market_symbol(args.src, args.dst)
    namespace = namespace_for_strategy_backtest(args.strategy, args)
    kwargs = strategy_kwargs_from_namespace(args.strategy, namespace)
    warmup_count = warmup_bar_count(args.strategy, kwargs)
    history = fetch_recent_closed_bars(symbol=symbol, resolution=args.interval, max_bars=warmup_count + 1)
    warmup_bars = history[:-1] if len(history) > 1 else []
    last_timestamp = int(warmup_bars[-1]["timestamp"]) if warmup_bars else None
    missed_bars: list = []
    if last_timestamp is not None:
        missed_bars = fetch_closed_bars_after(
            symbol=symbol,
            resolution=args.interval,
            after_open_unix_seconds=last_timestamp,
        )
    if bar_source is None:
        bar_source = incremental_bar_source(
            symbol=symbol,
            resolution=args.interval,
            last_bar_open_unix_seconds=last_timestamp,
            pending_bars=missed_bars,
        )
    capital_cap = float(getattr(args, "capital_cap", 0) or 0)
    if capital_cap <= 0:
        capital_cap = default_paper_initial_cash(args.dst)
    configure_risk_manager(
        RiskLimits(
            capital_cap=capital_cap,
            kill_switch=bool(getattr(args, "risk_kill_switch", False)),
        ),
    )
    algo = algorithm_from_args(args)
    trader = TerminalAlgorithmTrader(
        client,
        algo,
        bar_source=bar_source,
        execution=execution_from_args(args),
        market_symbol=symbol,
        warmup_bars=warmup_bars,
        capital_cap=capital_cap,
    )
    trader.strategy_id = args.strategy
    trader.emit_holds = getattr(args, EMIT_HOLDS, False)
    execution = execution_from_args(args)
    if execution.mode == "paper":
        initial_raw = getattr(args, "paper_initial_cash", None)
        initial_cash = float(initial_raw) if initial_raw is not None else default_paper_initial_cash(args.dst)
        if initial_cash <= 0:
            print("paper_initial_cash must be positive", file=sys.stderr)
            raise SystemExit(1)
        trader.paper_portfolio = PaperPortfolio(
            quote_cash=initial_cash,
            quote_currency=str(args.dst).strip().lower(),
            fee_rate=float(getattr(args, "paper_fee_rate", 0.0025) or 0.0025),
        )
        print_tick_event(
            {
                "event": "paper_wallet",
                "quote_currency": trader.paper_portfolio.quote_currency,
                "initial_cash": initial_cash,
                "fee_rate": trader.paper_portfolio.fee_rate,
                "symbol": symbol,
                "strategy_id": args.strategy,
            },
        )
    return trader
