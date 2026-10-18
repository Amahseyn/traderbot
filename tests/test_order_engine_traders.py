"""Paper trading through SimBroker and the live Hyperliquid order manager (mocked API)."""

from types import SimpleNamespace

import pytest

from traderbot.algorithms.strategies.perp_market_making import PerpMarketMakingAlgorithm
from traderbot.algorithms.strategies.scalp_dip import ScalpDipAlgorithm
from traderbot.backtesting.engine import run_backtest
from traderbot.hyperliquid.order_manager import HyperliquidOrderManager
from traderbot.hyperliquid.trading import HyperliquidOrderStatus, HyperliquidTradingError
from traderbot.terminal.paper_portfolio import PaperPortfolio


def _bar(ts, o, h, l, c):
    return {"timestamp": ts, "open": o, "high": h, "low": l, "close": c, "volume": 1.0, "symbol": "BTC"}


def _bars():
    bars = [_bar(i, 100, 100.1, 99.9, 100) for i in range(12)]
    bars.append(_bar(12, 99.2, 99.6, 99.1, 99.5))
    bars.append(_bar(13, 99.5, 99.6, 99.3, 99.5))
    bars.append(_bar(14, 99.5, 101.0, 99.4, 100.8))
    bars.append(_bar(15, 100.8, 100.9, 100.5, 100.6))
    return bars


def test_paper_portfolio_applies_slippage_to_market_fills():
    portfolio = PaperPortfolio(quote_cash=1000.0, quote_currency="usdt", fee_rate=0.0, slippage_rate=0.001)
    fill = portfolio.apply_fill("buy", 100.0)
    assert fill["price"] == pytest.approx(100.1)


def test_paper_order_engine_matches_backtest(monkeypatch):
    from traderbot.terminal import trader as trader_mod
    from traderbot.terminal.trader import TerminalAlgorithmTrader

    monkeypatch.setattr(trader_mod, "print_signal_event", lambda *a, **k: None)
    monkeypatch.setattr(trader_mod, "print_tick_event", lambda *a, **k: None)
    bars = _bars()
    kwargs = dict(scalp_order_mode="maker", entry_offset_pct=0.001, take_profit_pct=0.01)
    expected = run_backtest(ScalpDipAlgorithm(**kwargs), bars, initial_cash=1000.0, fee_rate=0.00045,
                            slippage_rate=0.0005)

    algo = ScalpDipAlgorithm(**kwargs)
    feed = iter(bars)
    fake = SimpleNamespace(
        algorithm=algo,
        paper_portfolio=PaperPortfolio(quote_cash=1000.0, quote_currency="usdt", fee_rate=0.00045,
                                       slippage_rate=0.0005),
        inventory=SimpleNamespace(spendable_quote=lambda cash: cash),
        market_symbol="BTC",
        strategy_id="scalp_dip",
        emit_holds=False,
        in_position=False,
    )
    fake._attach_paper_portfolio = lambda payload: None
    for bar in feed:
        TerminalAlgorithmTrader._step_paper_order_engine(fake, bar, 0)
    broker = fake._paper_broker
    assert [(t.action, t.price, t.reason) for t in broker.trades] == [
        (t.action, t.price, t.reason) for t in expected.trades
    ]
    assert fake.paper_portfolio.quote_cash == pytest.approx(broker.cash)


class FakeHL:
    """Records calls; ALO limits rest until ``fill(oid)``; stops never trigger by themselves."""

    def __init__(self, equity=1000.0):
        self.equity = equity
        self.position = 0.0
        self.orders = {}
        self.calls = []
        self.next_oid = 1

    def account_value(self):
        return self.equity

    def position_size(self, coin):
        return self.position

    def sz_decimals(self, coin):
        return 5

    def _response(self, oid, status="resting", size=0.0, px=0.0):
        body = {"resting": {"oid": oid}} if status == "resting" else {"filled": {"oid": oid, "totalSz": str(size), "avgPx": str(px)}}
        return {"status": "ok", "response": {"type": "order", "data": {"statuses": [body]}}}

    def limit_order(self, coin, *, is_buy, size, price, post_only=True, reduce_only=False):
        oid = self.next_oid
        self.next_oid += 1
        self.orders[oid] = {"is_buy": is_buy, "size": size, "price": price, "status": "open", "filled": 0.0,
                            "reduce_only": reduce_only, "kind": "limit"}
        self.calls.append(("limit", is_buy, size, price, reduce_only))
        return self._response(oid)

    def place_stop(self, coin, *, size, trigger_price, is_buy=False, sz_decimals=None):
        oid = self.next_oid
        self.next_oid += 1
        self.orders[oid] = {"is_buy": is_buy, "size": size, "price": trigger_price, "status": "open", "filled": 0.0,
                            "kind": "stop"}
        self.calls.append(("stop", is_buy, size, trigger_price))
        return self._response(oid)

    def market_open(self, coin, *, is_buy, size):
        self.calls.append(("market", is_buy, size))
        self.position += size if is_buy else -size
        return self._response(0, status="filled", size=size, px=100.0)

    def order_status(self, oid):
        order = self.orders[oid]
        return HyperliquidOrderStatus(status=order["status"], oid=oid, filled_size=order["filled"],
                                      avg_price=order["price"])

    def cancel(self, coin, oid):
        self.calls.append(("cancel", oid))
        if self.orders.get(oid, {}).get("status") != "open":
            raise HyperliquidTradingError("order was never placed, already canceled, or filled")
        self.orders[oid]["status"] = "canceled"

    def fill(self, oid):
        order = self.orders[oid]
        order["status"] = "filled"
        order["filled"] = order["size"]
        self.position += order["size"] if order["is_buy"] else -order["size"]


def test_live_manager_limit_entry_then_bracket_from_fill_price():
    api = FakeHL()
    algo = ScalpDipAlgorithm(scalp_order_mode="maker", entry_offset_pct=0.001, take_profit_pct=0.01,
                             stop_loss_pct=0.005)
    manager = HyperliquidOrderManager(coin="BTC", algorithm=algo, api=api)
    bars = _bars()
    for bar in bars[:13]:
        manager.step(bar)
    assert len(manager.resting) == 1
    entry = manager.resting[0]
    assert api.orders[entry.oid]["is_buy"] and api.orders[entry.oid]["price"] <= 99.5 * 0.999 + 1e-9
    api.fill(entry.oid)
    manager.step(bars[13])
    assert manager.resting == [] and manager.bracket is not None
    fill_px = api.orders[entry.oid]["price"]
    tp_call = [c for c in api.calls if c[0] == "limit"][-1]
    stop_call = [c for c in api.calls if c[0] == "stop"][-1]
    assert tp_call[1] is False and tp_call[4] is True  # reduce-only sell
    assert tp_call[3] == pytest.approx(fill_px * 1.01, rel=1e-4)
    assert stop_call[3] == pytest.approx(fill_px * 0.995, rel=1e-9)
    # Take profit fills on the exchange -> stop cancelled, strategy flat.
    api.fill(manager.bracket.tp_oid)
    sl_oid = manager.bracket.sl_oid
    manager.step(bars[14])
    assert manager.bracket is None and ("cancel", sl_oid) in api.calls
    assert algo._direction == 0


def test_live_manager_expires_unfilled_entry_after_ttl():
    api = FakeHL()
    algo = ScalpDipAlgorithm(scalp_order_mode="maker", entry_ttl_bars=1)
    manager = HyperliquidOrderManager(coin="BTC", algorithm=algo, api=api)
    bars = _bars()
    for bar in bars[:13]:
        manager.step(bar)
    oid = manager.resting[0].oid
    manager.step(bars[13])
    assert ("cancel", oid) in api.calls and algo._pending_entry == 0


def test_live_manager_requotes_pmm_each_bar_post_only():
    api = FakeHL()
    algo = PerpMarketMakingAlgorithm(half_spread_pct=0.002, vol_spread_mult=0.0, atr_period=1, trend_guard=False)
    manager = HyperliquidOrderManager(coin="BTC", algorithm=algo, api=api)
    bars = [_bar(i, 100, 100.1, 99.9, 100) for i in range(6)]
    for bar in bars:
        manager.step(bar)
    limits = [c for c in api.calls if c[0] == "limit"]
    assert limits and all(c[1] is True for c in limits)  # long-only: bids only
    assert limits[-1][3] == pytest.approx(99.8)
    # Previous quote cancelled before the new one is posted.
    assert sum(1 for c in api.calls if c[0] == "cancel") == len(limits) - 1
