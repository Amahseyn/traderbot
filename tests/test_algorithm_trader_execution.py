import pytest

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.nobitex.client import NobitexClient, NobitexClientError
from traderbot.risk.manager import RiskLimits
from traderbot.risk.runtime import configure_risk_manager
from traderbot.traders.bot_inventory import BotInventory
from traderbot.traders.execution import ExecutionPolicy
from traderbot.traders.strategies.algorithm_trader import AlgorithmTrader


class _SellAlgo(Algorithm):
    name = "sell_once"

    def __init__(self):
        self._done = False

    def reset(self) -> None:
        self._done = False

    def on_bar(self, bar: Bar) -> SignalAction:
        if self._done:
            return "hold"
        self._done = True
        return "sell"


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


def test_live_sell_keeps_inventory_when_order_rejected(keys, monkeypatch):
    configure_risk_manager(RiskLimits(stop_loss_pct=None), scope="BTCIRT")
    pub, priv = keys
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    inventory = BotInventory(quote_currency="rls", capital_cap=50_000.0)
    inventory.record_buy(quote_spent=50_000.0, base_received=0.5, price=100_000.0)

    def fake_add_market_order(_client, *, symbol, side, amount, price):
        return {"order": {"id": 99}}

    def reject_fill(_client, _order_id):
        raise NobitexClientError("order 99 ended with status rejected")

    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.add_market_order",
        fake_add_market_order,
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.wait_for_order_fill",
        reject_fill,
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.list_wallets",
        lambda _client: {"rls": 1_000_000.0, "btc": 0.5},
    )

    trader = AlgorithmTrader(
        client,
        _SellAlgo(),
        bar_source=lambda: _bar(),
        execution=ExecutionPolicy.live(),
        market_symbol="BTCIRT",
        inventory=inventory,
    )
    trader.in_position = True
    with pytest.raises(NobitexClientError):
        trader.step()
    assert trader.inventory.base_amount == 0.5
    assert trader.in_position is True


def test_execution_policy_kill_switch_allows_sell():
    policy = ExecutionPolicy(mode="live", kill_switch=True)
    assert not policy.permits("buy")
    assert policy.permits("sell")
