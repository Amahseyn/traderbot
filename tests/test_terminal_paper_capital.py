"""Paper live terminal: capital cap and equity reporting."""

from __future__ import annotations

import pytest

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.risk.manager import RiskLimits, RiskManager
from traderbot.terminal.paper_portfolio import PaperPortfolio
from traderbot.terminal.trader import TerminalAlgorithmTrader
from traderbot.traders.execution import ExecutionPolicy


class _BuyOnceAlgo(Algorithm):
    name = "buy_once"

    def __init__(self) -> None:
        self._fired = False

    def reset(self) -> None:
        self._fired = False

    def on_bar(self, bar: Bar) -> SignalAction:
        if self._fired:
            return "hold"
        self._fired = True
        return "buy"

    def sync_open_position(self, in_position: bool) -> None:
        return


def test_paper_equity_nonzero_when_fully_invested_and_mark_missing():
    portfolio = PaperPortfolio(quote_cash=1_000.0, quote_currency="usdt", fee_rate=0.0)
    portfolio.apply_fill("buy", 100.0)
    assert portfolio.quote_cash == 0.0
    assert portfolio.base_amount == 10.0

    snap = portfolio.snapshot(0.0)
    assert snap["equity"] == 1_000.0
    assert snap["quote_cash"] == 0.0


def test_paper_buy_respects_max_quote_spend():
    portfolio = PaperPortfolio(quote_cash=10_000.0, quote_currency="usdt", fee_rate=0.0)
    buy = portfolio.apply_fill("buy", 100.0, max_quote_spend=500.0)
    assert buy["filled"] is True
    assert buy["quote_spent"] == 500.0
    assert portfolio.quote_cash == 9_500.0
    assert portfolio.base_amount == 5.0


def test_paper_initial_cash_sets_capital_cap(keys, monkeypatch):
    from argparse import Namespace

    from traderbot.terminal.session import build_terminal_trader

    bar = {
        "timestamp": 1_700_000_000,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": 1.0,
        "symbol": "BTCUSDT",
    }
    monkeypatch.setattr(
        "traderbot.terminal.session.fetch_live_recent_closed_bars",
        lambda **_k: [bar],
    )
    monkeypatch.setattr(
        "traderbot.terminal.session.fetch_live_closed_bars_after",
        lambda **_k: [],
    )
    args = Namespace(
        strategy="sma_cross",
        src="btc",
        dst="usdt",
        interval="60",
        live=False,
        paper_initial_cash=750.0,
        exchange="hyperliquid",
        fast=5,
        slow=20,
        signal=9,
        period=14,
        oversold=30.0,
        overbought=70.0,
        num_std=2.0,
        price_confirm=False,
        no_auto_fine=False,
        fine_csv=None,
        no_buy=False,
        no_sell=False,
        emit_holds=False,
        capital_cap=0,
    )
    trader = build_terminal_trader(args, bar_source=lambda: None)
    assert trader.inventory.capital_cap == 750.0
    assert trader.paper_portfolio is not None
    assert trader.paper_portfolio.quote_cash == 750.0


def test_terminal_paper_buy_honors_capital_cap(keys):
    pub, priv = keys
    from traderbot.nobitex.client import NobitexClient

    bar: Bar = {
        "timestamp": 1_700_000_000,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": 1.0,
        "symbol": "BTCUSDT",
    }
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    trader = TerminalAlgorithmTrader(
        client,
        _BuyOnceAlgo(),
        bar_source=lambda: bar,
        execution=ExecutionPolicy.paper_only(),
        market_symbol="BTCUSDT",
        capital_cap=400.0,
        risk_manager=RiskManager(RiskLimits(capital_cap=400.0, stop_loss_pct=None)),
    )
    trader.paper_portfolio = PaperPortfolio(quote_cash=2_000.0, quote_currency="usdt", fee_rate=0.0)
    trader.strategy_id = "buy_once"

    trader.step()

    assert trader.paper_portfolio is not None
    assert trader.paper_portfolio.quote_cash == pytest.approx(1_600.0, abs=1.0)
    assert trader.paper_portfolio.base_amount == pytest.approx(4.0, abs=0.05)
    snap = trader.paper_portfolio.snapshot(100.0)
    assert snap["equity"] == pytest.approx(2_000.0, abs=2.0)

