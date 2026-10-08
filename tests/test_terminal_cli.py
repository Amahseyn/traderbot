import argparse
import json

from traderbot.terminal.catalog import catalog_dict
from traderbot.terminal.live import run_live
from traderbot.terminal.once import run_once
from traderbot.terminal.replay import run_replay


def test_terminal_catalog():
    out = catalog_dict(implemented_only=True)
    assert any(c["id"] == "run" for c in out["commands"])
    assert out["strategies"]
    assert all(s["implemented"] for s in out["strategies"])


def test_terminal_run_max_steps(keys, monkeypatch):
    pub, priv = keys
    bar = {
        "symbol": "BTCIRT",
        "resolution": "60",
        "timestamp": 1,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1.0,
    }
    seen: list[int] = []

    def source():
        seen.append(1)
        return bar if len(seen) == 1 else None

    class FakeBot:
        def __init__(self, traders, interval_sec=60.0):
            self.traders = traders

        def run(self, max_steps=None, should_stop=None):
            steps = max_steps or 1
            for _ in range(steps):
                if should_stop is not None and should_stop():
                    break
                for trader in self.traders:
                    trader.step()

    monkeypatch.setenv("NOBITEX_API_PUBLIC_KEY", pub)
    monkeypatch.setenv("NOBITEX_API_PRIVATE_KEY", priv)
    monkeypatch.setattr("traderbot.terminal.session.fetch_recent_closed_bars", lambda **_k: [])
    monkeypatch.setattr("traderbot.markets.market_data.fetch_latest_closed_bar", lambda **_k: bar)
    monkeypatch.setattr("traderbot.terminal.live.Bot", FakeBot)

    args = argparse.Namespace(
        src="btc",
        dst="rls",
        interval="60",
        strategy="sma_cross",
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
        poll_sec=0.01,
        max_steps=2,
        live=False,
        no_buy=False,
        no_sell=False,
        emit_holds=False,
    )
    run_live(args)


def test_terminal_once(monkeypatch, capsys):
    bar = {
        "symbol": "BTCIRT",
        "resolution": "60",
        "timestamp": 99,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 2.0,
        "volume": 1.0,
    }
    monkeypatch.setattr("traderbot.terminal.once.fetch_latest_closed_bar", lambda **_k: bar)
    monkeypatch.setattr("traderbot.terminal.once.fetch_recent_closed_bars", lambda **_k: [])
    args = argparse.Namespace(
        src="btc",
        dst="rls",
        interval="60",
        strategy="sma_cross",
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
        live=False,
        no_buy=False,
        no_sell=False,
        emit_holds=False,
    )
    run_once(args)
    row = json.loads(capsys.readouterr().out)
    assert row["event"] == "once"
    assert row["strategy_id"] == "sma_cross"
    assert row["timestamp"] == 99


def test_terminal_trader_live_delegates_orders(keys, monkeypatch):
    from traderbot.algorithms.base import Algorithm, Bar, SignalAction
    from traderbot.terminal.trader import TerminalAlgorithmTrader
    from traderbot.traders.execution import ExecutionPolicy

    class _BuyAlgo(Algorithm):
        def on_bar(self, bar: Bar) -> SignalAction:
            return "buy"

    pub, priv = keys
    client = __import__("traderbot.nobitex.client", fromlist=["NobitexClient"]).NobitexClient(
        pub,
        priv,
        request_fn=lambda *_a, **_k: None,
    )
    bar = {
        "timestamp": 1,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 100.0,
        "volume": 1.0,
        "symbol": "BTCIRT",
    }
    calls: list[str] = []

    def fake_add_market_order(_client, *, symbol, side, amount, price):
        calls.append(side)
        return {"status": "ok"}

    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.add_market_order",
        fake_add_market_order,
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.wait_for_order_fill",
        lambda *_a, **_k: {"status": "done", "matchedAmount": "0.01"},
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.add_stop_loss_order",
        lambda *_a, **_k: {"status": "ok"},
    )
    monkeypatch.setattr(
        "traderbot.traders.strategies.algorithm_trader.list_wallets",
        lambda _client: {"rls": 1000.0},
    )

    trader = TerminalAlgorithmTrader(
        client,
        _BuyAlgo(),
        bar_source=lambda: bar,
        execution=ExecutionPolicy.live(),
        market_symbol="BTCIRT",
    )
    trader.step()
    assert calls == ["buy"]


def test_terminal_trader_tick_on_no_new_bar(capsys):
    from traderbot.terminal.trader import TerminalAlgorithmTrader
    from traderbot.algorithms.base import Algorithm, Bar, SignalAction

    class _HoldAlgo(Algorithm):
        def on_bar(self, bar: Bar) -> SignalAction:
            return "hold"

    trader = TerminalAlgorithmTrader(
        None,
        _HoldAlgo(),
        bar_source=lambda: None,
        market_symbol="ARBUSDT",
    )
    trader.strategy_id = "sma_cross"
    trader.step()
    row = json.loads(capsys.readouterr().out)
    assert row["event"] == "tick"
    assert row["status"] == "no_new_bar"
    assert row["poll"] == 1


def test_terminal_trader_tick_on_hold_without_emit(capsys):
    from traderbot.terminal.trader import TerminalAlgorithmTrader
    from traderbot.algorithms.base import Algorithm, Bar, SignalAction

    class _HoldAlgo(Algorithm):
        def on_bar(self, bar: Bar) -> SignalAction:
            return "hold"

    bar = {
        "timestamp": 42,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1.0,
        "symbol": "ARBUSDT",
    }
    trader = TerminalAlgorithmTrader(
        None,
        _HoldAlgo(),
        bar_source=lambda: bar,
        market_symbol="ARBUSDT",
    )
    trader.strategy_id = "bollinger_mean_reversion"
    trader.step()
    row = json.loads(capsys.readouterr().out)
    assert row["event"] == "tick"
    assert row["status"] == "evaluated"
    assert row["signal"] == "hold"
    assert row["order"] is None


def test_terminal_replay(tmp_path, capsys):
    csv = tmp_path / "bars.csv"
    csv.write_text(
        "symbol,resolution,timestamp,datetime_utc,open,high,low,close,volume\n"
        "BTCIRT,60,1,1970-01-01T00:00:01+00:00,1,1,1,1,1\n"
        "BTCIRT,60,2,1970-01-01T00:00:02+00:00,2,2,2,2,1\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(
        csv=csv,
        max_bars=None,
        pace_sec=0.0,
        strategy="sma_cross",
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
        live=False,
        no_buy=False,
        no_sell=False,
        emit_holds=True,
    )
    run_replay(args)
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 2
    assert lines[0]["action"] == "hold"
