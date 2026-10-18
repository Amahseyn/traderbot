"""Hyperliquid live-execution sizing/stop regressions.

These exercise ``HyperliquidTerminalTrader._place_live_order`` with the exchange
calls monkeypatched, so no network access or credentials are required.
"""

from __future__ import annotations

import pytest

from traderbot.algorithms.base import OrderSize
from traderbot.algorithms.strategies.finrl_ema_intraday import FinrlEmaIntradayAlgorithm
from traderbot.risk.manager import RiskLimits, RiskManager
from traderbot.terminal import hyperliquid_trader as hlt
from traderbot.terminal.hyperliquid_trader import HyperliquidTerminalTrader

_BAR = {
    "timestamp": 0,
    "open": 100.0,
    "high": 101.0,
    "low": 99.0,
    "close": 100.0,
    "volume": 1.0,
}


def _trader(*, stop_loss_pct: float | None) -> HyperliquidTerminalTrader:
    return HyperliquidTerminalTrader(
        None,
        FinrlEmaIntradayAlgorithm(fast=2, slow=4),
        market_symbol="BTCUSDT",
        capital_cap=1000.0,
        risk_manager=RiskManager(RiskLimits(capital_cap=1000.0, stop_loss_pct=stop_loss_pct)),
    )


def _patch_exchange(monkeypatch) -> dict:
    calls: dict = {}

    def _open(coin, *, is_buy, size):
        calls["open"] = {"coin": coin, "is_buy": is_buy, "size": size}
        return {"ok": True}

    def _close(coin, *, size=None):
        calls["close"] = {"coin": coin, "size": size}
        return {"ok": True}

    def _stop(coin, *, size, trigger_price):
        calls["stop"] = {"coin": coin, "size": size, "trigger_price": trigger_price}
        return {"response": {"data": {"statuses": [{"resting": {"oid": 12345}}]}}}

    monkeypatch.setattr(hlt, "hyperliquid_account_value_usd", lambda: 1000.0)
    monkeypatch.setattr(hlt, "hyperliquid_market_open", _open)
    monkeypatch.setattr(hlt, "hyperliquid_market_close", _close)
    monkeypatch.setattr(hlt, "hyperliquid_place_stop", _stop)
    return calls


def test_hyperliquid_buy_honors_cash_fraction(monkeypatch) -> None:
    calls = _patch_exchange(monkeypatch)
    trader = _trader(stop_loss_pct=None)
    trader.hyperliquid_coin = "BTC"
    trader._pending_order_size = OrderSize(cash_fraction=0.25)

    trader._place_live_order("buy", _BAR, symbol="BTCUSDT")

    # 25% of the 1000 initial cash -> 250 quote -> 2.5 base at 100.
    assert calls["open"]["is_buy"] is True
    assert calls["open"]["size"] == pytest.approx(2.5)


def test_hyperliquid_sell_honors_target_exposure(monkeypatch) -> None:
    calls = _patch_exchange(monkeypatch)
    # Position-only account: 10 base worth 1000, no idle margin.
    monkeypatch.setattr(hlt, "hyperliquid_account_value_usd", lambda: 0.0)
    trader = _trader(stop_loss_pct=None)
    trader.hyperliquid_coin = "BTC"
    trader.inventory.record_buy(quote_spent=1000.0, base_received=10.0, price=100.0)
    # Target 50% exposure -> equity 1000 -> sell (10 - 0.5 * 1000 / 100) = 5 base.
    trader._pending_order_size = OrderSize(target_exposure=0.5)

    trader._place_live_order("sell", _BAR, symbol="BTCUSDT")

    assert calls["close"]["size"] == pytest.approx(5.0)


def test_hyperliquid_buy_places_protective_stop(monkeypatch) -> None:
    calls = _patch_exchange(monkeypatch)
    trader = _trader(stop_loss_pct=10.0)
    trader.hyperliquid_coin = "BTC"
    trader._pending_order_size = OrderSize(cash_fraction=0.25)

    trader._place_live_order("buy", _BAR, symbol="BTCUSDT")

    assert calls["stop"]["size"] == pytest.approx(2.5)
    assert calls["stop"]["trigger_price"] == pytest.approx(90.0)
    assert trader.active_stop_order_id == 12345


def test_hyperliquid_full_wallet_buy_when_no_order_size(monkeypatch) -> None:
    calls = _patch_exchange(monkeypatch)
    trader = _trader(stop_loss_pct=None)
    trader.hyperliquid_coin = "BTC"
    trader._pending_order_size = None

    trader._place_live_order("buy", _BAR, symbol="BTCUSDT")

    assert calls["open"]["size"] == pytest.approx(10.0, abs=0.01)
