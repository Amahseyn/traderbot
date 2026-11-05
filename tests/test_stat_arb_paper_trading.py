from __future__ import annotations

import pytest

from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.risk.cointegration_monitor import CointegrationHealthMonitor
from traderbot.risk.execution import PairExecutionRiskManager
from traderbot.risk.portfolio import PortfolioRiskManager, PortfolioRiskLimits
from traderbot.terminal.stat_arb_paper import StatArbPaperTrader


@pytest.fixture
def test_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_traderbot.db"
    monkeypatch.setenv("TRADERBOT_DB_PATH", str(db_path))
    from lab.store.database import open_database
    conn = open_database(db_path)
    conn.close()
    return db_path


def _make_bar(symbol: str, timestamp: int, price: float) -> dict:
    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "open": price,
        "high": price * 1.001,
        "low": price * 0.999,
        "close": price,
        "volume": 100.0,
    }


def test_two_leg_paper_lifecycle_fees_funding_and_emergency_exit(test_db):
    """Verify two-leg execution, fees, funding cost deduction, position tracking, and emergency exit."""
    algo = PairTradingAlgorithm(
        entry_threshold=1.5,
        exit_threshold=0.4,
        stop_threshold=3.5,
        lookback_period=20,
    )
    risk_manager = PortfolioRiskManager(
        limits=PortfolioRiskLimits(
            max_concurrent_pairs=3,
            portfolio_daily_loss_limit_pct=5.0,
        )
    )
    exec_manager = PairExecutionRiskManager(legging_policy="immediate_flatten")
    health_monitor = CointegrationHealthMonitor()

    trader = StatArbPaperTrader(
        pair_id="hyperliquid:BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        algorithm=algo,
        risk_manager=risk_manager,
        execution_manager=exec_manager,
        health_monitor=health_monitor,
        initial_cash=10_000.0,
        fee_rate=0.00045,
        slippage_rate=0.0005,
        persist=True,
    )

    assert trader.cash == 10_000.0
    assert not trader.has_open_position

    # 1. Feed baseline warmup bars (20 bars) with realistic variance
    for i in range(20):
        t = 1000 + i * 3600
        bar_a = _make_bar("BTC", t, 100.0 + (i % 5) * 0.5)
        bar_b = _make_bar("ETH", t, 50.0 + ((i + 2) % 4) * 0.3)
        trader.process_bar(bar_a, bar_b)

    assert not trader.has_open_position

    # 2. Trigger entry signal: Diverge prices so z-score is around 2.0
    t_entry = 1000 + 20 * 3600
    bar_a = _make_bar("BTC", t_entry, 102.5)
    bar_b = _make_bar("ETH", t_entry, 49.0)
    snap = trader.process_bar(bar_a, bar_b)

    assert trader.has_open_position
    pos = trader.position_state
    assert pos is not None
    assert pos.status == "OPEN"
    # Fee was deducted for both legs
    assert trader.total_fees > 0.0
    assert trader.cash < 10_000.0

    # 3. Process discrete funding payment on the next bar
    t_funding = 1000 + 21 * 3600
    # Positive funding rate on long, negative on short
    snap_funding = trader.process_bar(
        _make_bar("BTC", t_funding, 102.4),
        _make_bar("ETH", t_funding, 49.1),
        funding_rates=(0.0001, -0.0001),
    )
    assert trader.total_funding_paid != 0.0 or trader.total_funding_received != 0.0
    assert trader.has_open_position

    # 4. Emergency Exit
    exit_snap = trader.emergency_flatten(reason="operator_triggered_emergency")
    assert not trader.has_open_position
    assert exit_snap["status"] == "EMERGENCY_EXIT"
    from traderbot.analysis.pairs.persistence import fetch_pair_paper_position_history
    hist = fetch_pair_paper_position_history(pair_id="hyperliquid:BTC-ETH")
    assert len(hist) == 1
    assert hist[0]["status"] == "EMERGENCY_EXIT"


def test_failed_leg_immediate_unwind_policy(test_db):
    """Verify that when leg B fails, immediate_flatten unwinds leg A cleanly."""
    algo = PairTradingAlgorithm(
        entry_threshold=1.0,
        exit_threshold=0.2,
        lookback_period=10,
    )
    risk_manager = PortfolioRiskManager()
    exec_manager = PairExecutionRiskManager(legging_policy="immediate_flatten")
    health_monitor = CointegrationHealthMonitor()

    trader = StatArbPaperTrader(
        pair_id="hyperliquid:BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        algorithm=algo,
        risk_manager=risk_manager,
        execution_manager=exec_manager,
        health_monitor=health_monitor,
        initial_cash=10_000.0,
        simulate_leg_b_failure=True,
    )

    # Feed bars to trigger entry
    for i in range(10):
        t = 1000 + i * 3600
        trader.process_bar(_make_bar("BTC", t, 100.0), _make_bar("ETH", t, 50.0))

    # Entry divergence bar
    t_div = 1000 + 10 * 3600
    snap = trader.process_bar(_make_bar("BTC", t_div, 120.0), _make_bar("ETH", t_div, 50.0))

    # Since leg B failed, immediate_flatten unwound Leg A; no position remains held
    assert not trader.has_open_position
    assert trader.unwound_legs_count == 1
