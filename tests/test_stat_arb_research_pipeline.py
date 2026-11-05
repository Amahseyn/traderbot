from __future__ import annotations

import pytest

from traderbot.analysis.pairs.pipeline import (
    StatArbPipelineConfig,
    run_stat_arb_research_pipeline,
)


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


def test_full_13_step_research_pipeline_end_to_end(test_db):
    """Verify execution of the complete 13-step research pipeline from universe discovery to backtesting and persistence."""
    # Synthetic cointegrated series
    n = 150
    timestamps = [1000 + i * 3600 for i in range(n)]
    import numpy as np

    np.random.seed(42)
    # Common random walk
    w = np.cumsum(np.random.normal(0, 1.0, n))
    spread = np.zeros(n)
    for i in range(1, n):
        spread[i] = 0.6 * spread[i - 1] + np.random.normal(0, 0.5)

    p_a = 1000.0 + w + spread
    p_b = 500.0 + 0.5 * w

    bars_a = [_make_bar("BTC", t, float(p)) for t, p in zip(timestamps, p_a)]
    bars_b = [_make_bar("ETH", t, float(p)) for t, p in zip(timestamps, p_b)]
    bars_by_symbol = {"BTC": bars_a, "ETH": bars_b}

    config = StatArbPipelineConfig(
        exchange="hyperliquid",
        timeframe="60",
        top_n=5,
        run_backtest=True,
        persist=True,
    )

    result = run_stat_arb_research_pipeline(
        config=config,
        bars_by_symbol=bars_by_symbol,
        job_id="test-job-pipeline-1",
    )

    assert result.run_id == "test-job-pipeline-1"
    assert "BTC" in result.tradable_markets
    assert "ETH" in result.tradable_markets
    assert len(result.candidates) >= 1
    assert result.summary["candidates_generated"] >= 1
    # Multi-pair or pair backtest results generated
    assert result.backtest_results is not None
    assert "hyperliquid:BTC-ETH" in result.backtest_results
    bt_res = result.backtest_results["hyperliquid:BTC-ETH"]
    assert "return_pct" in bt_res
    assert "equity_curve" in bt_res
    assert len(bt_res["equity_curve"]) > 0

    # Verify persistence in SQLite
    from lab.store.database import open_database
    conn = open_database()
    try:
        run_row = conn.execute("SELECT id, status FROM pair_discovery_runs WHERE id = ?", (result.run_id,)).fetchone()
        assert run_row is not None
        assert run_row[1] == "completed"

        # Check candidate table
        cand_count = conn.execute("SELECT COUNT(*) FROM pair_candidates WHERE run_id = ?", (result.run_id,)).fetchone()[0]
        assert cand_count >= 1
    finally:
        conn.close()

