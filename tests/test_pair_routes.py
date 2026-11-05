from __future__ import annotations

from pathlib import Path
import numpy as np
import pytest

from lab.store.database import init_database, open_database
from traderbot.analysis.pairs.engine import PairDiscoveryConfig, PairDiscoveryEngine


def _generate_cointegrated_bars(n_bars: int = 150, symbol_a: str = "BTC", symbol_b: str = "ETH"):
    rng = np.random.default_rng(42)
    b_innovations = rng.normal(0, 0.01, size=n_bars)
    log_b = 4.0 + np.cumsum(b_innovations)

    spread = np.zeros(n_bars)
    noise = rng.normal(0, 0.008, size=n_bars)
    for t in range(1, n_bars):
        spread[t] = 0.85 * spread[t - 1] + noise[t]

    log_a = 0.5 + 1.2 * log_b + spread
    price_a = np.exp(log_a)
    price_b = np.exp(log_b)

    bars_a = []
    bars_b = []
    for i in range(n_bars):
        ts = 1_000_000 + i * 3600
        bars_a.append({
            "symbol": symbol_a,
            "resolution": "60",
            "timestamp": ts,
            "open": float(price_a[i]),
            "high": float(price_a[i] * 1.002),
            "low": float(price_a[i] * 0.998),
            "close": float(price_a[i]),
            "volume": 10_000.0,
        })
        bars_b.append({
            "symbol": symbol_b,
            "resolution": "60",
            "timestamp": ts,
            "open": float(price_b[i]),
            "high": float(price_b[i] * 1.002),
            "low": float(price_b[i] * 0.998),
            "close": float(price_b[i]),
            "volume": 10_000.0,
        })
    return bars_a, bars_b


def test_pair_discovery_api_routes(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from lab.app import create_app

    test_db = tmp_path / "test_lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(test_db))
    conn = open_database(test_db)
    init_database(conn)
    conn.close()

    app = create_app(database_path=test_db)
    client = TestClient(app)

    bars_btc, bars_eth = _generate_cointegrated_bars()
    bars_by_symbol = {"BTC": bars_btc, "ETH": bars_eth}

    # 1. Test POST /api/pairs/discovery with direct bars
    post_res = client.post(
        "/api/pairs/discovery",
        json={
            "exchange": "hyperliquid",
            "timeframe": "60",
            "top_n": 5,
            "bars_by_symbol": bars_by_symbol,
        },
    )
    assert post_res.status_code == 200, post_res.text
    data = post_res.json()
    assert data["status"] == "completed"
    assert "summary" in data
    assert len(data["ranked_pairs"]) >= 1

    ranked = data["ranked_pairs"][0]
    expected_fields = [
        "pair_id", "exchange", "symbol_a", "symbol_b", "timeframe",
        "correlation", "cointegration_status", "hedge_ratio", "half_life_bars",
        "liquidity_score", "stability_score", "pair_quality_score",
        "ranking_position", "qualification_status", "rejection_reasons", "last_updated",
    ]
    for f in expected_fields:
        assert f in ranked, f"Missing field {f} in ranked pair"

    # 2. Test GET /api/pairs/rankings
    get_rankings = client.get("/api/pairs/rankings?exchange=hyperliquid&timeframe=60&top_n=5")
    assert get_rankings.status_code == 200
    rankings_data = get_rankings.json()
    assert rankings_data["count"] >= 1
    assert rankings_data["pairs"][0]["pair_id"] == "hyperliquid:BTC-ETH"
    for f in expected_fields:
        assert f in rankings_data["pairs"][0], f"Missing field {f} in rankings"

    # 3. Test GET /api/pairs/history
    get_hist = client.get("/api/pairs/history?pair_id=hyperliquid:BTC-ETH")
    assert get_hist.status_code == 200
    hist_data = get_hist.json()
    assert hist_data["pair_id"] == "hyperliquid:BTC-ETH"
    assert hist_data["count"] >= 1
    assert hist_data["history"][0]["change_type"] == "new_entry"

    # 4. Test GET /api/pairs/runs
    get_runs = client.get("/api/pairs/runs?exchange=hyperliquid")
    assert get_runs.status_code == 200
    runs_data = get_runs.json()
    assert runs_data["count"] >= 1
    assert runs_data["runs"][0]["exchange"] == "hyperliquid"
    assert "summary" in runs_data["runs"][0]

    # 5. Test POST /api/jobs/pair-discovery
    job_res = client.post(
        "/api/jobs/pair-discovery",
        json={
            "exchange": "hyperliquid",
            "timeframe": "60",
            "top_n": 5,
            "bars_by_symbol": bars_by_symbol,
        },
    )
    assert job_res.status_code == 200
    assert job_res.json()["status"] == "queued"
    assert "id" in job_res.json()

    # 6. Test POST /api/strategies/pair-backtest with cointegration parameters
    backtest_res = client.post(
        "/api/strategies/pair-backtest",
        json={
            "exchange": "hyperliquid",
            "dominant_bars": bars_btc,
            "hedge_bars": bars_eth,
            "lookback_period": 20,
            "entry_threshold": 1.5,
            "exit_threshold": 0.4,
            "stop_threshold": 3.5,
            "hedge_ratio": 1.2,
            "intercept": 0.5,
            "spread_model": "cointegration",
            "sizing_model": "hedge_ratio",
        },
    )
    assert backtest_res.status_code == 200
    bt_data = backtest_res.json()
    assert bt_data["exchange"] == "hyperliquid"
    assert bt_data["spread_model"] == "cointegration"
    assert bt_data["sizing_model"] == "hedge_ratio"
    assert "equity_curve" in bt_data
    assert "spread_curve" in bt_data
    assert "z_score_curve" in bt_data
    assert "exposure_curve" in bt_data

