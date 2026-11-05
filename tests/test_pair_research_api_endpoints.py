from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lab.app import create_app


@pytest.fixture
def client(monkeypatch, tmp_path):
    import lab.security as lab_security

    db_path = tmp_path / "test_traderbot.db"
    monkeypatch.setenv("TRADERBOT_DB_PATH", str(db_path))
    monkeypatch.setenv("LAB_API_DISABLE_AUTH", "0")
    monkeypatch.setenv("LAB_API_TOKEN", "test-token-12345")
    lab_security._TOKEN = None
    app = create_app(database_path=db_path)
    return TestClient(app)


def _auth_headers():
    return {"Authorization": "Bearer test-token-12345"}


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


def test_all_research_and_paper_endpoints(client):
    """Verify research and paper endpoints with authentication and pagination."""
    # 1. Trigger sync discovery run
    n = 60
    ts = [1000 + i * 3600 for i in range(n)]
    bars_by_symbol = {
        "BTC": [_make_bar("BTC", t, 100.0 + (i % 5) * 0.5) for i, t in enumerate(ts)],
        "ETH": [_make_bar("ETH", t, 50.0 + (i % 3) * 0.25) for i, t in enumerate(ts)],
    }
    disc_resp = client.post(
        "/api/pairs/discovery",
        json={"sync": True, "bars_by_symbol": bars_by_symbol},
        headers=_auth_headers(),
    )
    assert disc_resp.status_code == 200
    disc_data = disc_resp.json()
    assert disc_data["status"] == "completed"

    # 2. GET /api/pairs/markets
    m_resp = client.get("/api/pairs/markets")
    assert m_resp.status_code == 200
    m_data = m_resp.json()
    assert "tradable_markets" in m_data
    assert "rejected_markets" in m_data

    # 3. GET /api/pairs/candidates
    c_resp = client.get("/api/pairs/candidates")
    assert c_resp.status_code == 200
    c_data = c_resp.json()
    assert "candidates" in c_data

    # 4. GET /api/pairs/correlation
    corr_resp = client.get("/api/pairs/correlation")
    assert corr_resp.status_code == 200
    corr_data = corr_resp.json()
    assert "candidates" in corr_data or "pairs" in corr_data

    # 5. GET /api/pairs/cointegration
    coint_resp = client.get("/api/pairs/cointegration")
    assert coint_resp.status_code == 200
    coint_data = coint_resp.json()
    assert "results" in coint_data

    # 6. GET /api/pairs/rankings
    r_resp = client.get("/api/pairs/rankings")
    assert r_resp.status_code == 200

    # 7. GET /api/pairs/paper/positions
    pos_resp = client.get("/api/pairs/paper/positions")
    assert pos_resp.status_code == 200
    pos_data = pos_resp.json()
    assert "active_positions" in pos_data

    # 8. POST /api/pairs/paper/emergency-exit requires auth
    unauth_exit = client.post("/api/pairs/paper/emergency-exit", json={"pair_id": "hyperliquid:BTC-ETH"})
    assert unauth_exit.status_code == 401

    auth_exit = client.post(
        "/api/pairs/paper/emergency-exit",
        json={"pair_id": "hyperliquid:BTC-ETH", "reason": "test_emergency"},
        headers=_auth_headers(),
    )
    assert auth_exit.status_code == 200

    # 9. POST /api/strategies/pair-walk-forward
    wf_resp = client.post(
        "/api/strategies/pair-walk-forward",
        json={
            "dominant_bars": bars_by_symbol["BTC"],
            "hedge_bars": bars_by_symbol["ETH"],
            "train_bars": 30,
            "test_bars": 15,
            "purge_bars": 5,
            "param_grid": {"entry_threshold": [1.5, 2.0], "exit_threshold": [0.4, 0.8]},
        },
        headers=_auth_headers(),
    )
    assert wf_resp.status_code == 200
    wf_data = wf_resp.json()
    assert "folds" in wf_data
