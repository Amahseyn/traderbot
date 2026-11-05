from __future__ import annotations

import sqlite3
import pytest

from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.analysis.pairs.pipeline import StatArbPipelineConfig, run_stat_arb_research_pipeline
from traderbot.analysis.pairs.persistence import (
    fetch_active_pair_paper_positions,
    record_pair_paper_position,
    update_pair_paper_position,
)
from traderbot.risk.cointegration_monitor import CointegrationHealthMonitor
from traderbot.risk.execution import PairExecutionRiskManager
from traderbot.risk.portfolio import PortfolioRiskManager
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
        "resolution": "60",
        "timestamp": timestamp,
        "open": price,
        "high": price * 1.002,
        "low": price * 0.998,
        "close": price,
        "volume": 1000.0,
    }


def test_restart_recovery_from_database(test_db):
    """Verify state recovery after process restart: active positions reload from SQLite."""
    # 1. Simulate process 1 creating an open paper position and exiting
    pos_id = record_pair_paper_position(
        pair_id="hyperliquid:BTC-ETH",
        entry_spread=-0.035,
        entry_z_score=-1.85,
        leg_a_qty=0.25,
        leg_b_qty=-4.15,
        entry_price_a=64000.0,
        entry_price_b=3450.0,
        snapshot={"status": "OPEN", "pair_id": "hyperliquid:BTC-ETH", "initial_half_life": 12.0},
    )
    assert pos_id is not None

    # 2. Simulate process 2 restarting: initialize new PortfolioRiskManager and reload
    active_positions = fetch_active_pair_paper_positions()
    assert len(active_positions) == 1
    reloaded_pos = active_positions[0]
    assert reloaded_pos["id"] == pos_id
    assert reloaded_pos["pair_id"] == "hyperliquid:BTC-ETH"
    assert reloaded_pos["leg_a_qty"] == pytest.approx(0.25)
    assert reloaded_pos["leg_b_qty"] == pytest.approx(-4.15)

    risk_mgr = PortfolioRiskManager()
    from traderbot.risk.pair_models import PairRiskState
    recovered_state = PairRiskState(
        pair_id=reloaded_pos["pair_id"],
        symbol_a="BTC",
        symbol_b="ETH",
        leg_a_qty=reloaded_pos["leg_a_qty"],
        leg_b_qty=reloaded_pos["leg_b_qty"],
        entry_price_a=reloaded_pos["entry_price_a"],
        entry_price_b=reloaded_pos["entry_price_b"],
        current_price_a=reloaded_pos["entry_price_a"],
        current_price_b=reloaded_pos["entry_price_b"],
    )
    risk_mgr.register_pair(recovered_state)

    assert "hyperliquid:BTC-ETH" in risk_mgr.active_pairs
    assert risk_mgr.active_pairs["hyperliquid:BTC-ETH"].gross_notional > 0


def test_idempotent_duplicate_pipeline_jobs(test_db):
    """Verify running duplicate jobs with same run_id updates idempotently without database errors."""
    n = 60
    timestamps = [1000 + i * 3600 for i in range(n)]
    bars_by_symbol = {
        "BTC": [_make_bar("BTC", t, 100.0 + (i % 3) * 0.1) for i, t in enumerate(timestamps)],
        "ETH": [_make_bar("ETH", t, 50.0 + (i % 3) * 0.05) for i, t in enumerate(timestamps)],
    }
    cfg = StatArbPipelineConfig(exchange="hyperliquid", timeframe="60", run_backtest=False)

    # First run
    res1 = run_stat_arb_research_pipeline(cfg, bars_by_symbol=bars_by_symbol, job_id="idempotent-job-1")
    assert res1.run_id == "idempotent-job-1"

    # Second run with same job_id (re-submission / retry)
    res2 = run_stat_arb_research_pipeline(cfg, bars_by_symbol=bars_by_symbol, job_id="idempotent-job-1")
    assert res2.run_id == "idempotent-job-1"

    # Database state is intact
    from lab.store.database import open_database
    conn = open_database()
    try:
        count = conn.execute("SELECT COUNT(*) FROM pair_discovery_runs WHERE id = 'idempotent-job-1'").fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_partial_fill_and_legging_abort_unwind(test_db):
    """Verify that when Leg B fails completely or times out, Leg A is unwound and no delta leaks."""
    algo = PairTradingAlgorithm(
        entry_threshold=1.0,
        exit_threshold=0.2,
        lookback_period=10,
    )
    risk_mgr = PortfolioRiskManager()
    exec_mgr = PairExecutionRiskManager(legging_policy="immediate_flatten")
    health_mon = CointegrationHealthMonitor()

    trader = StatArbPaperTrader(
        pair_id="hyperliquid:BTC-ETH",
        symbol_a="BTC",
        symbol_b="ETH",
        algorithm=algo,
        risk_manager=risk_mgr,
        execution_manager=exec_mgr,
        health_monitor=health_mon,
        initial_cash=10_000.0,
        simulate_leg_b_failure=True,
    )

    for i in range(10):
        t = 1000 + i * 3600
        trader.process_bar(_make_bar("BTC", t, 100.0), _make_bar("ETH", t, 50.0))

    # Entry divergence bar
    snap = trader.process_bar(_make_bar("BTC", 50000, 120.0), _make_bar("ETH", 50000, 50.0))
    # Unwind took place
    assert not trader.has_open_position
    assert trader.unwound_legs_count == 1
    assert trader.cash < 10_000.0  # Fees paid for entry & unwind

