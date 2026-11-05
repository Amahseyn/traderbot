from __future__ import annotations

import sqlite3
import pytest

from lab.store.database import open_database
from traderbot.analysis.pairs.persistence import (
    close_pair_paper_position,
    fetch_active_pair_paper_positions,
    fetch_pair_execution_events,
    fetch_pair_paper_position_history,
    fetch_pair_risk_decisions,
    fetch_pair_strategy_signals,
    record_pair_execution_event,
    record_pair_paper_position,
    record_pair_risk_decision,
    record_pair_strategy_signal,
    update_pair_paper_position,
)


@pytest.fixture
def test_db(monkeypatch, tmp_path):
    db_path = tmp_path / "test_traderbot.db"
    monkeypatch.setenv("TRADERBOT_DB_PATH", str(db_path))
    conn = open_database(db_path)
    conn.close()
    return db_path


def test_persist_signals_positions_and_risk_decisions(test_db):
    """Verify persisting strategy signals, paper positions, execution events, and risk decisions."""
    # 1. Strategy Signal
    sig_id = record_pair_strategy_signal(
        pair_id="hyperliquid:BTC-ETH",
        action="enter_long_spread",
        spread=-0.045,
        z_score=-2.35,
        dominant_price=65000.0,
        hedge_price=3500.0,
        hedge_ratio=1.12,
        dominant_qty=0.15,
        hedge_qty=2.79,
        metadata={"source": "unit_test"},
    )
    assert sig_id is not None
    signals = fetch_pair_strategy_signals(pair_id="hyperliquid:BTC-ETH")
    assert len(signals) == 1
    assert signals[0]["action"] == "enter_long_spread"
    assert signals[0]["z_score"] == pytest.approx(-2.35)

    # 2. Paper Position Open & Update
    pos_id = record_pair_paper_position(
        pair_id="hyperliquid:BTC-ETH",
        entry_spread=-0.045,
        entry_z_score=-2.35,
        leg_a_qty=0.15,
        leg_b_qty=-2.79,
        entry_price_a=65000.0,
        entry_price_b=3500.0,
        snapshot={"status": "OPEN", "initial_half_life": 14.5},
    )
    assert pos_id is not None

    active_positions = fetch_active_pair_paper_positions()
    assert len(active_positions) == 1
    assert active_positions[0]["id"] == pos_id
    assert active_positions[0]["status"] == "OPEN"

    # Update mark-to-market
    update_pair_paper_position(
        position_id=pos_id,
        unrealized_pnl=42.50,
        total_fees=12.20,
        total_funding=-3.40,
        snapshot={"status": "OPEN", "current_z_score": -1.10},
    )
    updated_pos = fetch_active_pair_paper_positions()[0]
    assert updated_pos["unrealized_pnl"] == pytest.approx(42.50)
    assert updated_pos["total_fees"] == pytest.approx(12.20)
    assert updated_pos["total_funding"] == pytest.approx(-3.40)

    # 3. Execution Events
    event_id = record_pair_execution_event(
        position_id=pos_id,
        pair_id="hyperliquid:BTC-ETH",
        leg="dominant",
        action="buy",
        requested_qty=0.15,
        filled_qty=0.15,
        fill_price=65005.0,
        fee=6.10,
        slippage=5.0,
        execution_status="FILLED",
        notes="maker entry",
    )
    assert event_id is not None
    events = fetch_pair_execution_events(pair_id="hyperliquid:BTC-ETH")
    assert len(events) == 1
    assert events[0]["leg"] == "dominant"
    assert events[0]["execution_status"] == "FILLED"

    # 4. Risk Decisions
    dec_id = record_pair_risk_decision(
        pair_id="hyperliquid:BTC-ETH",
        check_type="HEALTH_MONITOR",
        verdict="APPROVED",
        reason="cointegration_stable",
        metrics={"half_life": 14.5, "adf_stat": -3.85},
    )
    assert dec_id is not None
    decisions = fetch_pair_risk_decisions(pair_id="hyperliquid:BTC-ETH")
    assert len(decisions) == 1
    assert decisions[0]["verdict"] == "APPROVED"

    # 5. Close Position
    close_pair_paper_position(
        position_id=pos_id,
        exit_spread=-0.005,
        exit_z_score=-0.20,
        exit_price_a=65800.0,
        exit_price_b=3480.0,
        realized_pnl=145.0,
        total_fees=24.40,
        total_funding=-4.50,
        status="CLOSED",
        snapshot={"status": "CLOSED"},
    )
    assert len(fetch_active_pair_paper_positions()) == 0
    history = fetch_pair_paper_position_history(pair_id="hyperliquid:BTC-ETH")
    assert len(history) == 1
    assert history[0]["status"] == "CLOSED"
    assert history[0]["realized_pnl"] == pytest.approx(145.0)

