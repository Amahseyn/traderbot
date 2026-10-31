"""Unit tests for Phase 0 safety invariants from the audit plan:
- Venue compatibility validation (shorts on spot rejected).
- Fail-closed protective stops with emergency flatten on failure.
- Account-level PortfolioRiskManager multi-symbol limits.
- Two-way reconciliation report and divergence detection.
"""

from __future__ import annotations

import pytest
from types import SimpleNamespace

from traderbot.algorithms.base import Algorithm, Bar, OrderSize, OrderSpec, SignalAction
from traderbot.hyperliquid.order_manager import HyperliquidOrderManager
from traderbot.hyperliquid.trading import HyperliquidOrderStatus, HyperliquidTradingError
from traderbot.risk.manager import RiskLimits, RiskManager
from traderbot.risk.portfolio import PortfolioRiskLimits, PortfolioRiskManager
from traderbot.risk.runtime import (
    clear_risk_managers,
    configure_portfolio_risk_manager,
    get_portfolio_risk_manager,
)
from traderbot.terminal import hyperliquid_trader as hlt
from traderbot.terminal.hyperliquid_trader import HyperliquidTerminalTrader
from traderbot.traders.bot_inventory import BotInventory
from traderbot.traders.inventory_reconcile import audit_and_reconcile_inventory
from traderbot.traders.strategies.algorithm_trader import AlgorithmTrader


# -----------------------------------------------------------------------------------------
# 1. Capability & Venue Validation
# -----------------------------------------------------------------------------------------

class _DummyShortAlgo(Algorithm):
    name = "dummy_short"
    allow_short = True

    def on_bar(self, bar: Bar) -> SignalAction:
        return "sell"


def test_short_strategy_rejected_on_spot_venue():
    algo = _DummyShortAlgo()
    with pytest.raises(ValueError, match="requires short capability"):
        algo.validate_venue_compatibility("nobitex")

    with pytest.raises(ValueError, match="requires short capability"):
        algo.validate_venue_compatibility("spot")

    # Allowed on Hyperliquid perps
    algo.validate_venue_compatibility("hyperliquid")


def test_algorithm_trader_rejects_short_algo_at_init():
    algo = _DummyShortAlgo()
    with pytest.raises(ValueError, match="requires short capability"):
        AlgorithmTrader(
            client=SimpleNamespace(),
            algorithm=algo,
            bar_source=lambda: None,
            market_symbol="BTCIRT",
        )


# -----------------------------------------------------------------------------------------
# 2. Protective Stop Fail-Closed & Emergency Flatten
# -----------------------------------------------------------------------------------------

class _DummyBracketAlgo(Algorithm):
    name = "dummy_bracket"

    def on_bar(self, bar: Bar) -> SignalAction:
        return "buy"

    def order_spec(self) -> OrderSpec:
        return OrderSpec(order_type="market", stop_loss_pct=2.0)


def test_order_manager_emergency_flatten_on_stop_failure():
    events: list[dict] = []
    fake_calls: list[tuple] = []
    current_pos = [0.0]

    def _market_open(coin, *, is_buy, size):
        fake_calls.append(("market_open", is_buy, size))
        current_pos[0] = size if is_buy else 0.0
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": {"oid": 101, "totalSz": str(size), "avgPx": "100.0"}}]},
            },
        }

    def _place_stop(*args, **kwargs):
        raise HyperliquidTradingError("API connection rejected stop order")

    api = SimpleNamespace(
        account_value=lambda: 1000.0,
        position_size=lambda coin: current_pos[0],
        sz_decimals=lambda coin: 4,
        order_status=lambda oid: HyperliquidOrderStatus(status="open", oid=oid),
        limit_order=lambda *a, **k: None,
        market_open=_market_open,
        place_stop=_place_stop,
        cancel=lambda coin, oid: None,
    )

    manager = HyperliquidOrderManager(
        coin="BTC",
        algorithm=_DummyBracketAlgo(),
        api=api,
        emit=lambda e: events.append(e),
        emergency_flatten_on_stop_failure=True,
    )

    bar = {"timestamp": 1, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0}
    manager.step(bar)

    # 1. Entry was bought
    assert ("market_open", True, 10.0) in fake_calls
    # 2. Emergency close was immediately sent to flatten the position
    assert ("market_open", False, 10.0) in fake_calls
    # 3. Manager is in halted state
    assert manager.halted is True
    assert "emergency_flatten" in manager.halt_reason

    # 4. Verify events emitted
    event_names = [e.get("event") for e in events]
    assert "bracket_error" in event_names
    assert "emergency_flatten" in event_names
    assert "emergency_flatten_filled" in event_names

    # 5. Subsequent steps return hold while halted
    assert manager.step(bar) == "hold"


def test_hyperliquid_trader_emergency_flatten_on_stop_failure(monkeypatch):
    calls: list[str] = []

    def _open(coin, *, is_buy, size):
        calls.append("open")
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": {"oid": 1, "totalSz": str(size), "avgPx": "100.0"}}]},
            },
        }

    def _close(coin, *, size=None):
        calls.append("close")
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": {"oid": 2, "totalSz": str(size), "avgPx": "100.0"}}]},
            },
        }

    def _stop_fail(*args, **kwargs):
        calls.append("stop_fail")
        raise HyperliquidTradingError("Stop trigger placement network failure")

    monkeypatch.setattr(hlt, "hyperliquid_account_value_usd", lambda: 1000.0)
    monkeypatch.setattr(hlt, "hyperliquid_market_open", _open)
    monkeypatch.setattr(hlt, "hyperliquid_market_close", _close)
    monkeypatch.setattr(hlt, "hyperliquid_place_stop", _stop_fail)
    monkeypatch.setattr(hlt, "hyperliquid_sz_decimals", lambda coin: 4)

    trader = HyperliquidTerminalTrader(
        None,
        _DummyBracketAlgo(),
        market_symbol="BTCUSDT",
        capital_cap=1000.0,
        risk_manager=RiskManager(RiskLimits(stop_loss_pct=2.0)),
    )
    trader.hyperliquid_coin = "BTC"

    bar = {"timestamp": 1, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0}

    with pytest.raises(Exception, match="emergency flatten executed"):
        trader._place_live_order("buy", bar, symbol="BTCUSDT")

    assert calls == ["open", "stop_fail", "close"]
    assert trader.risk.halted is True
    assert trader.inventory.base_amount == 0.0


# -----------------------------------------------------------------------------------------
# 3. Account-Level / Portfolio Risk Manager
# -----------------------------------------------------------------------------------------

def test_portfolio_risk_manager_daily_loss_halts_all_symbols():
    clear_risk_managers()
    port_risk = configure_portfolio_risk_manager(
        PortfolioRiskLimits(portfolio_daily_loss_limit_pct=5.0)
    )
    port_risk.reset_session(10_000.0)

    # Initial entry is allowed
    verdict1 = port_risk.evaluate_entry(
        "BTCUSDT", requested_notional=1000.0, total_equity=10_000.0
    )
    assert verdict1.allowed is True
    port_risk.update_position("BTCUSDT", True)

    # Account equity drops 6% due to BTC loss
    verdict_eth = port_risk.evaluate_entry(
        "ETHUSDT", requested_notional=1000.0, total_equity=9_300.0
    )
    assert verdict_eth.allowed is False
    assert port_risk.halted is True
    assert verdict_eth.reason == "portfolio_daily_loss_limit"

    clear_risk_managers()


def test_portfolio_risk_manager_max_concurrent_positions():
    clear_risk_managers()
    port_risk = configure_portfolio_risk_manager(
        PortfolioRiskLimits(max_concurrent_positions=2)
    )
    port_risk.reset_session(10_000.0)

    # Position 1
    assert port_risk.evaluate_entry("BTC", requested_notional=1000.0, total_equity=10_000.0).allowed
    port_risk.update_position("BTC", True)

    # Position 2
    assert port_risk.evaluate_entry("ETH", requested_notional=1000.0, total_equity=10_000.0).allowed
    port_risk.update_position("ETH", True)

    # Position 3 exceeds limit
    verdict_sol = port_risk.evaluate_entry("SOL", requested_notional=1000.0, total_equity=10_000.0)
    assert verdict_sol.allowed is False
    assert "max_concurrent_positions_reached" in verdict_sol.reason

    # Closing Position 1 permits Position 3
    port_risk.update_position("BTC", False)
    assert port_risk.evaluate_entry("SOL", requested_notional=1000.0, total_equity=10_000.0).allowed

    clear_risk_managers()


def test_portfolio_risk_manager_max_gross_exposure():
    clear_risk_managers()
    port_risk = configure_portfolio_risk_manager(
        PortfolioRiskLimits(max_gross_exposure_equity=1.0)
    )
    port_risk.reset_session(10_000.0)

    # 8,000 existing notional + 3,000 requested = 11,000 > 10,000 (1.0x equity)
    verdict = port_risk.evaluate_entry(
        "BTC", requested_notional=3_000.0, total_equity=10_000.0, current_gross_notional=8_000.0
    )
    assert verdict.allowed is False
    assert "max_gross_exposure_exceeded" in verdict.reason

    clear_risk_managers()


# -----------------------------------------------------------------------------------------
# 4. Two-Way Inventory Reconciliation
# -----------------------------------------------------------------------------------------

def test_audit_reconciliation_downward():
    inv = BotInventory(quote_currency="usdt", capital_cap=1000.0)
    inv.record_buy(quote_spent=100.0, base_received=1.0, price=100.0)

    report = audit_and_reconcile_inventory(inv, exchange_base=0.6, mark_price=100.0)
    assert report.reconciled_down is True
    assert report.surplus_detected is False
    assert report.bot_base == pytest.approx(0.6)
    assert report.discrepancy == pytest.approx(-0.4)


def test_audit_reconciliation_surplus_detection():
    inv = BotInventory(quote_currency="usdt", capital_cap=1000.0)
    inv.record_buy(quote_spent=100.0, base_received=0.5, price=100.0)

    report = audit_and_reconcile_inventory(inv, exchange_base=1.5, mark_price=100.0)
    assert report.reconciled_down is False
    assert report.surplus_detected is True
    # Bot inventory remains unchanged (pre-existing surplus not adopted)
    assert inv.base_amount == pytest.approx(0.5)
    assert report.discrepancy == pytest.approx(1.0)
    assert "Exchange surplus detected" in report.message


# -----------------------------------------------------------------------------------------
# 5. Phase 1: UTC Rollover, Spread Fail-Closed, Attribution, Experimental Strategy
# -----------------------------------------------------------------------------------------

def test_risk_manager_utc_rollover():
    from datetime import datetime, timezone, timedelta
    from traderbot.risk.manager import utc_today

    manager = RiskManager(RiskLimits())
    assert manager.session_date == datetime.now(timezone.utc).date()
    # Simulate past date
    manager.session_date = utc_today() - timedelta(days=1)
    manager.halted = True
    manager.halt_reason = "daily_loss_limit"
    manager._roll_session_if_new_day(1000.0)
    assert manager.session_date == utc_today()
    assert manager.halted is False


def test_hyperliquid_trader_spread_fail_closed(monkeypatch):
    class _SpreadAlgo(Algorithm):
        max_spread_pct = 0.001

        def on_bar(self, bar: Bar) -> SignalAction:
            return "buy"

    def _failing_book(coin):
        raise RuntimeError("Websocket/REST book disconnected")

    monkeypatch.setattr(hlt, "hyperliquid_best_bid_ask", _failing_book)
    trader = HyperliquidTerminalTrader(
        None,
        _SpreadAlgo(),
        market_symbol="BTCUSDT",
    )
    bar = {"timestamp": 1, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0}
    trader.prepare_for_bar(bar)
    # Book failure sets spread_pct to infinity so filters fail closed
    assert bar["spread_pct"] == float("inf")


def test_hyperliquid_trader_records_fill_attribution(monkeypatch):
    def _open(coin, *, is_buy, size):
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"statuses": [{"filled": {"oid": 1, "totalSz": str(size), "avgPx": "100.25"}}]},
            },
        }

    monkeypatch.setattr(hlt, "hyperliquid_account_value_usd", lambda: 1000.0)
    monkeypatch.setattr(hlt, "hyperliquid_market_open", _open)
    monkeypatch.setattr(hlt, "hyperliquid_sz_decimals", lambda coin: 4)

    trader = HyperliquidTerminalTrader(
        None,
        _DummyBracketAlgo(),
        market_symbol="BTCUSDT",
        capital_cap=1000.0,
        risk_manager=RiskManager(RiskLimits(stop_loss_pct=None)),
    )
    trader.hyperliquid_coin = "BTC"

    bar = {"timestamp": 1, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1.0}
    trader._place_live_order("buy", bar, symbol="BTCUSDT")

    assert trader.last_fill_attribution is not None
    assert trader.last_fill_attribution["action"] == "buy"
    assert trader.last_fill_attribution["expected_price"] == 100.0
    assert trader.last_fill_attribution["realized_price"] == 100.25
    assert trader.last_fill_attribution["slippage_pct"] == pytest.approx(0.25)


def test_scalp_dip_marked_experimental():
    from traderbot.algorithms.strategies.scalp_dip import ScalpDipAlgorithm

    algo = ScalpDipAlgorithm()
    assert algo.is_experimental is True


# -----------------------------------------------------------------------------------------
# 6. Risk State Persistence (A-12)
# -----------------------------------------------------------------------------------------

def test_risk_manager_file_persistence(tmp_path):
    state_file = tmp_path / "risk_state.json"
    manager = RiskManager(RiskLimits(daily_loss_limit_pct=4.0))
    manager.reset_session(10_000.0)
    manager.update_mark(9_500.0)
    manager.halted = True
    manager.halt_reason = "daily_loss_limit"

    manager.save_to_file(state_file)
    assert state_file.is_file()

    # Create fresh manager and restore
    new_manager = RiskManager(RiskLimits(daily_loss_limit_pct=4.0))
    loaded = new_manager.load_from_file(state_file)
    assert loaded is True
    assert new_manager.day_start_equity == 10_000.0
    assert new_manager.last_equity == 9_500.0
    assert new_manager.halted is True
    assert new_manager.halt_reason == "daily_loss_limit"


def test_portfolio_risk_manager_file_persistence(tmp_path):
    state_file = tmp_path / "portfolio_risk.json"
    port = PortfolioRiskManager(PortfolioRiskLimits(portfolio_max_drawdown_pct=10.0))
    port.reset_session(50_000.0)
    port.update_position("BTCUSDT", True)
    port.update_position("ETHUSDT", True)
    port.update_mark(48_000.0)

    port.save_to_file(state_file)
    assert state_file.is_file()

    fresh_port = PortfolioRiskManager()
    loaded = fresh_port.load_from_file(state_file)
    assert loaded is True
    assert fresh_port.day_start_equity == 50_000.0
    assert fresh_port.last_equity == 48_000.0
    assert fresh_port.active_positions == {"BTCUSDT", "ETHUSDT"}


# -----------------------------------------------------------------------------------------
# 7. Backtest Cost Attribution & Conservative Fill Model (A-06, A-07, A-10)
# -----------------------------------------------------------------------------------------

def test_backtest_result_cost_and_execution_summary():
    from traderbot.algorithms.strategies.sma_cross import SmaCrossAlgorithm
    from traderbot.backtesting.engine import run_backtest

    bars = [
        {"timestamp": i * 60, "open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i, "close": 100.5 + i, "volume": 10.0, "symbol": "BTCUSDT"}
        for i in range(10)
    ]
    result = run_backtest(
        SmaCrossAlgorithm(fast=2, slow=4),
        bars,
        fee_rate=0.00045,
        maker_fee_rate=0.00015,
        slippage_rate=0.0005,
        execution="next_open",
        exchange="hyperliquid",
    )
    summary = result.cost_and_execution_summary()
    assert summary["execution"] == "next_open"
    assert summary["is_causal"] is True
    assert summary["exchange"] == "hyperliquid"
    assert summary["fee_rate"] == 0.00045
    assert summary["maker_fee_rate"] == 0.00015
    assert summary["slippage_rate"] == 0.0005


def test_limit_fill_penetration_buffer():
    from traderbot.backtesting.fills import limit_fill_price

    bar = {"open": 100.0, "high": 100.5, "low": 99.9, "close": 100.0}
    # Standard: low (99.9) < limit (100.0) -> fills
    assert limit_fill_price("buy", 100.0, bar, penetration_pct=0.0) == 100.0
    # Conservative: requires 0.2% penetration (below 99.8) -> 99.9 does NOT fill!
    assert limit_fill_price("buy", 100.0, bar, penetration_pct=0.002) is None


def test_grid_algorithm_max_exposure_cap():
    from traderbot.algorithms.strategies.grid import GridAlgorithm

    grid = GridAlgorithm(grid_levels=5, max_exposure=0.5)
    # Band 0 would normally give 1.0 (100%) exposure, but is capped at 0.5 (50%)
    assert grid._exposure_for(0) == 0.5
    assert grid._exposure_for(4) == 0.0


