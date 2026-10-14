import pytest

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.nobitex.client import NobitexClient
from traderbot.risk.manager import RiskLimits
from traderbot.risk.runtime import configure_risk_manager
from traderbot.traders.execution import ExecutionPolicy
from traderbot.traders.strategies.algorithm_trader import AlgorithmTrader


class _BuyThenSellAlgo(Algorithm):
    def __init__(self) -> None:
        self._step = 0

    def reset(self) -> None:
        self._step = 0

    def on_bar(self, bar: Bar) -> SignalAction:
        self._step += 1
        if self._step == 1:
            return "buy"
        if self._step == 2:
            return "sell"
        return "hold"


def _bar() -> Bar:
    return {
        "timestamp": 1,
        "open": 100.0,
        "high": 100.0,
        "low": 100.0,
        "close": 100.0,
        "volume": 1.0,
        "symbol": "BTCIRT",
    }


def test_sell_cancels_active_stop_before_market_order(keys, monkeypatch):
    configure_risk_manager(RiskLimits(stop_loss_pct=2.0), scope="BTCIRT")
    pub, priv = keys
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    cancel_calls: list[int] = []
    market_sides: list[str] = []
    step = 0

    def bar_source():
        nonlocal step
        step += 1
        if step > 2:
            return None
        return _bar()

    def fake_add_market_order(_client, *, symbol, side, amount, price):
        market_sides.append(side)
        return {"order": {"id": 10 if side == "buy" else 11}}

    def fake_stop(_client, **kwargs):
        return {"order": {"id": 99}}

    def fake_cancel(_client, order_id, **kwargs):
        cancel_calls.append(int(order_id))
        return {"status": "ok"}

    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.add_market_order",
        fake_add_market_order,
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.add_stop_loss_order",
        fake_stop,
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.cancel_open_order",
        fake_cancel,
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.wait_for_order_fill",
        lambda *_a, **_k: {"status": "done", "matchedAmount": "0.01"},
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.list_wallets",
        lambda _client: {"rls": 1_000_000.0, "btc": 0.01},
    )

    trader = AlgorithmTrader(
        client,
        _BuyThenSellAlgo(),
        bar_source=bar_source,
        execution=ExecutionPolicy.live(),
        market_symbol="BTCIRT",
    )
    trader.step()
    assert trader.active_stop_order_id == 99
    trader.step()
    assert cancel_calls == [99]
    assert market_sides == ["buy", "sell"]
    assert trader.active_stop_order_id is None
