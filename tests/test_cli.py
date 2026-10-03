import json

import pytest

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.nobitex.client import NobitexClient
from traderbot.traders.execution import ExecutionPolicy
from traderbot.traders.strategies.algorithm_trader import AlgorithmTrader


def test_root_cli_no_args_without_keys_prints_help(capsys, monkeypatch):
    from traderbot.cli import main

    monkeypatch.delenv("NOBITEX_API_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("NOBITEX_API_PRIVATE_KEY", raising=False)
    monkeypatch.setattr("sys.stdin", type("S", (), {"isatty": lambda self: False})())
    main([])
    out = capsys.readouterr().out
    assert "export" in out
    assert "strategy" in out


def test_root_cli_help(capsys):
    from traderbot.cli import main

    main(["--help"])
    out = capsys.readouterr().out
    assert "export" in out
    assert "strategy" in out
    assert "interface" in out
    assert "auth" in out
    assert "cli" in out
    assert "terminal" in out


def test_root_cli_unknown_command():
    from traderbot.cli import main

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


def test_ml_catalog_implemented_only_flag(capsys):
    from traderbot.cli.ml import main

    main(["catalog", "--implemented-only"])
    out = capsys.readouterr().out
    rows = json.loads(out)
    assert rows
    assert all(r["implemented"] for r in rows)
    assert {r["id"] for r in rows} == {"lightgbm", "chronos"}
