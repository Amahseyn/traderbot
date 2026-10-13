
import pytest

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.nobitex.client import NobitexClient
from traderbot.traders.execution import ExecutionPolicy
from traderbot.traders.strategies.algorithm_trader import AlgorithmTrader


def test_lab_serve_help(capsys):
    from lab.serve import main

    with pytest.raises(SystemExit):
        main(["--help"])


def test_lab_serve_unknown_subcommand():
    from lab.serve import main

    with pytest.raises(SystemExit):
        main(["not-a-command"])


class _BuyAlgo(Algorithm):
    name = "buy_once"

    def __init__(self):
        self._done = False

    def reset(self) -> None:
        self._done = False

    def on_bar(self, bar: Bar) -> SignalAction:
        if self._done:
            return "hold"
        self._done = True
        return "buy"


def test_execution_policy_paper_routes_to_on_paper_signal(keys):
    pub, priv = keys
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    bar = {"timestamp": 1, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
    calls: list[str] = []

    class T(AlgorithmTrader):
        def on_paper_signal(self, action, _bar):
            calls.append(action)

        def on_signal(self, action, _bar):
            calls.append(f"live:{action}")

    trader = T(
        client,
        _BuyAlgo(),
        bar_source=lambda: bar,
        execution=ExecutionPolicy.paper_only(),
    )
    trader.step()
    assert calls == ["buy"]


def test_capital_cap_limits_live_buy_spend(keys, monkeypatch):
    from traderbot.risk.manager import RiskLimits
    from traderbot.risk.runtime import configure_risk_manager

    configure_risk_manager(RiskLimits(capital_cap=50_000.0, stop_loss_pct=None))
    pub, priv = keys
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    bar = {
        "timestamp": 1,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 100.0,
        "volume": 1.0,
        "symbol": "BTCIRT",
    }
    recorded: list[tuple[str, str | float]] = []

    def fake_add_market_order(_client, *, symbol, side, amount, price):
        recorded.append((side, amount))
        return {"order": {"id": 1}}

    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.add_market_order",
        fake_add_market_order,
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.wait_for_order_fill",
        lambda _client, _order_id: {"matchedAmount": recorded[-1][1]},
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.list_wallets",
        lambda _client: {"rls": 1_000_000.0, "btc": 0.0},
    )

    trader = AlgorithmTrader(
        client,
        _BuyAlgo(),
        bar_source=lambda: bar,
        execution=ExecutionPolicy.live(),
        market_symbol="BTCIRT",
        capital_cap=50_000.0,
    )
    trader.step()
    assert recorded[0][0] == "buy"
    assert 490.0 < float(recorded[0][1]) < 500.0


def test_execution_policy_live_routes_to_on_signal(keys):
    pub, priv = keys
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    bar = {"timestamp": 1, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
    calls: list[str] = []

    class T(AlgorithmTrader):
        def on_signal(self, action, _bar):
            calls.append(action)

    trader = T(
        client,
        _BuyAlgo(),
        bar_source=lambda: bar,
        execution=ExecutionPolicy.live(),
    )
    trader.step()
    assert calls == ["buy"]

