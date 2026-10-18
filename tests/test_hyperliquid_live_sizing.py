"""Hyperliquid live-execution sizing/stop regressions.

These exercise ``HyperliquidTerminalTrader._place_live_order`` with the exchange
calls monkeypatched, so no network access or credentials are required.
"""

from __future__ import annotations

import pytest

from traderbot.algorithms.base import OrderSize
from traderbot.algorithms.strategies.finrl_ema_intraday import FinrlEmaIntradayAlgorithm
from traderbot.hyperliquid import trading as hl_trading
from traderbot.nobitex.client import NobitexClientError
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


def _filled(size: float, px: float, oid: int = 1) -> dict:
    return {
        "status": "ok",
        "response": {"type": "order", "data": {"statuses": [{"filled": {"totalSz": str(size), "avgPx": str(px), "oid": oid}}]}},
    }


def _trader(*, stop_loss_pct: float | None) -> HyperliquidTerminalTrader:
    return HyperliquidTerminalTrader(
        None,
        FinrlEmaIntradayAlgorithm(fast=2, slow=4),
        market_symbol="BTCUSDT",
        capital_cap=1000.0,
        risk_manager=RiskManager(RiskLimits(capital_cap=1000.0, stop_loss_pct=stop_loss_pct)),
    )


def _patch_exchange(monkeypatch, *, fill_px: float = 100.0, sz_decimals: int = 3) -> dict:
    calls: dict = {}

    def _open(coin, *, is_buy, size):
        calls["open"] = {"coin": coin, "is_buy": is_buy, "size": size}
        return _filled(size, fill_px)

    def _close(coin, *, size=None):
        calls["close"] = {"coin": coin, "size": size}
        return _filled(size, fill_px, oid=2)

    def _stop(coin, *, size, trigger_price, sz_decimals=None):
        calls["stop"] = {"coin": coin, "size": size, "trigger_price": trigger_price}
        return {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 12345}}]}}}

    monkeypatch.setattr(hlt, "hyperliquid_account_value_usd", lambda: 1000.0)
    monkeypatch.setattr(hlt, "hyperliquid_market_open", _open)
    monkeypatch.setattr(hlt, "hyperliquid_market_close", _close)
    monkeypatch.setattr(hlt, "hyperliquid_place_stop", _stop)
    monkeypatch.setattr(hlt, "hyperliquid_sz_decimals", lambda coin: sz_decimals)
    monkeypatch.setattr(hlt, "hyperliquid_cancel_order", lambda coin, oid: calls.setdefault("cancel", []).append(oid))
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
    # Perp account value (1000) already includes the 10-base position worth 1000.
    trader = _trader(stop_loss_pct=None)
    trader.hyperliquid_coin = "BTC"
    trader.inventory.record_buy(quote_spent=1000.0, base_received=10.0, price=100.0)
    # Target 50% exposure -> equity 1000 -> sell (10 - 0.5 * 1000 / 100) = 5 base.
    trader._pending_order_size = OrderSize(target_exposure=0.5)

    trader._place_live_order("sell", _BAR, symbol="BTCUSDT")

    assert calls["close"]["size"] == pytest.approx(5.0)
    assert trader.inventory.base_amount == pytest.approx(5.0)


def test_hyperliquid_buy_places_protective_stop_from_fill_price(monkeypatch) -> None:
    calls = _patch_exchange(monkeypatch, fill_px=100.5)
    trader = _trader(stop_loss_pct=10.0)
    trader.hyperliquid_coin = "BTC"
    trader._pending_order_size = OrderSize(cash_fraction=0.25)

    trader._place_live_order("buy", _BAR, symbol="BTCUSDT")

    assert calls["stop"]["size"] == pytest.approx(2.5)
    # Stop measured from the actual average fill (100.5), not the bar close (100).
    assert calls["stop"]["trigger_price"] == pytest.approx(90.45)
    assert trader.active_stop_order_id == 12345
    assert trader.inventory.avg_entry_price == pytest.approx(100.5)


def test_hyperliquid_full_wallet_buy_when_no_order_size(monkeypatch) -> None:
    calls = _patch_exchange(monkeypatch)
    trader = _trader(stop_loss_pct=None)
    trader.hyperliquid_coin = "BTC"
    trader._pending_order_size = None

    trader._place_live_order("buy", _BAR, symbol="BTCUSDT")

    assert calls["open"]["size"] == pytest.approx(10.0, abs=0.01)


def test_hyperliquid_size_rounded_to_sz_decimals(monkeypatch) -> None:
    calls = _patch_exchange(monkeypatch, sz_decimals=5)
    trader = _trader(stop_loss_pct=None)
    trader.hyperliquid_coin = "BTC"
    trader._pending_order_size = OrderSize(cash_fraction=0.5)
    bar = dict(_BAR, close=67012.37)
    trader._place_live_order("buy", bar, symbol="BTCUSDT")
    size = calls["open"]["size"]
    assert size == pytest.approx(0.00746)
    assert round(size, 5) == size


def test_hyperliquid_below_min_notional_is_rejected(monkeypatch) -> None:
    calls = _patch_exchange(monkeypatch)
    trader = _trader(stop_loss_pct=None)
    trader.hyperliquid_coin = "BTC"
    trader._pending_order_size = OrderSize(cash_fraction=0.005)  # 5 USD
    with pytest.raises(NobitexClientError, match="minimum"):
        trader._place_live_order("buy", _BAR, symbol="BTCUSDT")
    assert "open" not in calls
    assert trader.inventory.base_amount == 0


def test_hyperliquid_per_order_error_does_not_record_buy(monkeypatch) -> None:
    _patch_exchange(monkeypatch)

    def _rejected(coin, *, is_buy, size):
        response = {"status": "ok", "response": {"type": "order", "data": {"statuses": [{"error": "Insufficient margin"}]}}}
        hl_trading.first_order_status(response)  # real helper raises on per-order error
        return response

    monkeypatch.setattr(hlt, "hyperliquid_market_open", _rejected)
    trader = _trader(stop_loss_pct=None)
    trader.hyperliquid_coin = "BTC"
    with pytest.raises(NobitexClientError, match="Insufficient margin"):
        trader._place_live_order("buy", _BAR, symbol="BTCUSDT")
    assert trader.inventory.base_amount == 0


def test_hyperliquid_partial_fill_records_filled_size(monkeypatch) -> None:
    _patch_exchange(monkeypatch)
    monkeypatch.setattr(hlt, "hyperliquid_market_open", lambda coin, *, is_buy, size: _filled(size / 2, 101.0))
    trader = _trader(stop_loss_pct=None)
    trader.hyperliquid_coin = "BTC"
    trader._pending_order_size = OrderSize(cash_fraction=0.5)
    trader._place_live_order("buy", _BAR, symbol="BTCUSDT")
    assert trader.inventory.base_amount == pytest.approx(2.5)
    assert trader.inventory.avg_entry_price == pytest.approx(101.0)
    assert trader.inventory.quote_reserved == pytest.approx(252.5)


def test_hyperliquid_equity_not_double_counted(monkeypatch) -> None:
    """Round trip with a budget equal to the account must not trip the drawdown halt."""
    _patch_exchange(monkeypatch)
    trader = _trader(stop_loss_pct=None)
    trader.hyperliquid_coin = "BTC"
    trader._place_live_order("buy", _BAR, symbol="BTCUSDT")
    trader._pending_order_size = None
    trader._place_live_order("sell", _BAR, symbol="BTCUSDT")
    assert trader.risk.peak_equity == pytest.approx(1000.0)
    trader._place_live_order("buy", _BAR, symbol="BTCUSDT")
    assert not trader.risk.halted
    assert trader.inventory.base_amount > 0


def test_signed_position_and_status_parsing() -> None:
    statuses = hl_trading.parse_order_statuses(
        {"status": "ok", "response": {"data": {"statuses": [{"resting": {"oid": 9}}, {"error": "x"}]}}}
    )
    assert statuses[0].status == "resting" and statuses[0].oid == 9
    assert statuses[1].status == "error"
    with pytest.raises(hl_trading.HyperliquidTradingError):
        hl_trading.first_order_status({"status": "err", "response": "bad"})
    with pytest.raises(hl_trading.HyperliquidTradingError):
        hl_trading.first_order_status({"status": "ok", "response": {"data": {"statuses": [{"error": "min $10"}]}}})


def test_price_and_size_rounding() -> None:
    assert hl_trading.round_hyperliquid_price(67012.37, 5) == 67012.0
    assert hl_trading.round_hyperliquid_price(60300.45, 5, round_up=True) == 60301.0
    assert hl_trading.round_hyperliquid_price(2345.678, 4) == 2345.6
    assert hl_trading.round_hyperliquid_price(0.123456789, 0) == 0.12345
    assert hl_trading.round_hyperliquid_size(0.0074626865, 5) == 0.00746
    with pytest.raises(hl_trading.HyperliquidTradingError):
        hl_trading.prepare_order_size("BTC", 0.0001, price=60000.0, sz_decimals=5)
    assert hl_trading.prepare_order_size("BTC", 0.0001, price=60000.0, sz_decimals=5, reduce_only=True) == 0.0001
