from __future__ import annotations

import argparse
import sys

from traderbot.algorithms.registry import strategy_kwargs_from_namespace
from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest
from traderbot.algorithms.warmup import warmup_bar_count
from traderbot.markets.exchange import (
    DEFAULT_LIVE_EXCHANGE,
    fetch_live_closed_bars_after,
    fetch_live_recent_closed_bars,
    live_incremental_bar_source,
    live_market_symbol,
    normalize_live_exchange,
)
from traderbot.risk.runtime import configure_risk_manager
from traderbot.risk.manager import RiskLimits
from traderbot.nobitex.client import NobitexClient, NobitexClientError
from traderbot.hyperliquid.market_data import hyperliquid_coin_from_src
from traderbot.hyperliquid.credentials import hyperliquid_wallet_configured
from traderbot.terminal.events import print_tick_event
from traderbot.terminal.hyperliquid_trader import HyperliquidTerminalTrader
from traderbot.terminal.namespace_keys import EMIT_HOLDS
from traderbot.terminal.paper_portfolio import PaperPortfolio, default_paper_initial_cash
from traderbot.utils.trading_costs import DEFAULT_TRADE_FEE_RATE
from traderbot.terminal.trader import TerminalAlgorithmTrader
from traderbot.terminal.utils import algorithm_from_args, execution_from_args
from traderbot.traders.strategies.algorithm_trader import BarSource


def _exchange_from_args(args: argparse.Namespace) -> str:
    return normalize_live_exchange(getattr(args, "exchange", None) or DEFAULT_LIVE_EXCHANGE)


def build_terminal_trader(
    args: argparse.Namespace,
    *,
    bar_source: BarSource | None,
) -> TerminalAlgorithmTrader:
    exchange = _exchange_from_args(args)
    symbol = live_market_symbol(exchange, args.src, args.dst)
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
    warmup_bars = history[:-1] if len(history) > 1 else []
    last_timestamp = int(warmup_bars[-1]["timestamp"]) if warmup_bars else None
    missed_bars: list = []
    if last_timestamp is not None:
        missed_bars = fetch_live_closed_bars_after(
            exchange=exchange,
            src=args.src,
            dst=args.dst,
            resolution=args.interval,
            after_open_unix_seconds=last_timestamp,
        )
    if bar_source is None:
        bar_source = live_incremental_bar_source(
            exchange=exchange,
            src=args.src,
            dst=args.dst,
            resolution=args.interval,
            last_bar_open_unix_seconds=last_timestamp,
            pending_bars=missed_bars,
        )
    dst = str(args.dst).strip().lower()
    if exchange == "hyperliquid" and dst in ("rls", "irt"):
        dst = "usdt"
    capital_cap = float(getattr(args, "capital_cap", 0) or 0)
    if capital_cap <= 0:
        capital_cap = default_paper_initial_cash(dst)
    execution = execution_from_args(args)
    if execution.mode == "live":
        budget_raw = getattr(args, "live_quote_budget", None)
        if budget_raw is not None:
            budget = float(budget_raw)
            if budget <= 0:
                print("live_quote_budget must be positive", file=sys.stderr)
                raise SystemExit(1)
            capital_cap = budget
    configure_risk_manager(
        RiskLimits(
            capital_cap=capital_cap,
            kill_switch=bool(getattr(args, "risk_kill_switch", False)),
        ),
        scope=symbol,
    )
    algo = algorithm_from_args(args)

    if exchange == "hyperliquid":
        if execution.mode == "live" and not hyperliquid_wallet_configured():
            print("HYPERLIQUID_WALLET_ADDRESS is not set", file=sys.stderr)
            raise SystemExit(1)
        client = NobitexClient("", "", request_fn=lambda *_a, **_k: None)
        trader: TerminalAlgorithmTrader = HyperliquidTerminalTrader(
            client,
            algo,
            bar_source=bar_source,
            execution=execution_from_args(args),
            market_symbol=symbol,
            warmup_bars=warmup_bars,
            capital_cap=capital_cap,
            risk_scope=symbol,
        )
        trader.hyperliquid_coin = hyperliquid_coin_from_src(args.src)
    else:
        try:
            client = NobitexClient.from_env()
        except NobitexClientError as e:
            print(e, file=sys.stderr)
            raise SystemExit(1) from e
        trader = TerminalAlgorithmTrader(
            client,
            algo,
            bar_source=bar_source,
            execution=execution_from_args(args),
            market_symbol=symbol,
            warmup_bars=warmup_bars,
            capital_cap=capital_cap,
            risk_scope=symbol,
        )

    trader.strategy_id = args.strategy
    trader.emit_holds = getattr(args, EMIT_HOLDS, False)
    print_tick_event(
        {
            "event": "live_exchange",
            "exchange": exchange,
            "symbol": symbol,
            "strategy_id": args.strategy,
        },
    )
    if execution.mode == "live" and getattr(args, "live_quote_budget", None) is not None:
        quote_currency = "usdt" if exchange == "hyperliquid" else dst
        print_tick_event(
            {
                "event": "live_quote_budget",
                "quote_currency": quote_currency,
                "quote_budget": capital_cap,
                "symbol": symbol,
                "strategy_id": args.strategy,
            },
        )
    if execution.mode == "paper":
        initial_raw = getattr(args, "paper_initial_cash", None)
        initial_cash = float(initial_raw) if initial_raw is not None else default_paper_initial_cash(dst)
        if initial_cash <= 0:
            print("paper_initial_cash must be positive", file=sys.stderr)
            raise SystemExit(1)
        trader.paper_portfolio = PaperPortfolio(
            quote_cash=initial_cash,
            quote_currency=dst,
            fee_rate=float(
                getattr(args, "paper_fee_rate", None) or DEFAULT_TRADE_FEE_RATE
            ),
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
