"""Tests for Market Cap service and Lab API routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lab.app import create_app
from traderbot.marketcap.service import MarketCapService


@pytest.fixture(autouse=True)
def _fast_marketcap_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    # Avoid real network latency during unit test suite
    import requests
    original_get = requests.get

    def fake_get(url: str, *args, **kwargs):
        raise requests.RequestException("Offline unit test")

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_get)


def test_marketcap_service_seed_fallback() -> None:
    service = MarketCapService(ttl_seconds=10.0, request_timeout_seconds=0.1)
    # Global metrics
    global_metrics = service.get_global_metrics(force_refresh=False)
    assert "total_market_cap_usd" in global_metrics
    assert global_metrics["total_market_cap_usd"] > 0
    assert "btc_dominance_pct" in global_metrics

    # Coins list
    response = service.get_coins(page=1, limit=10, category="all")
    assert response["total"] > 0
    assert len(response["coins"]) <= 10
    first_coin = response["coins"][0]
    assert "symbol" in first_coin
    assert "name" in first_coin
    assert "market_cap" in first_coin
    assert "current_price" in first_coin


def test_marketcap_service_search_and_filter() -> None:
    service = MarketCapService()
    # Search BTC
    btc_result = service.get_coins(search="BTC")
    assert btc_result["total"] >= 1
    found_symbols = [coin["symbol"] for coin in btc_result["coins"]]
    assert "BTC" in found_symbols

    # Coin detail
    detail = service.get_coin_details("btc")
    assert detail is not None
    assert detail["symbol"] == "BTC"
    assert detail["name"].lower() == "bitcoin"


def test_marketcap_service_categories() -> None:
    service = MarketCapService()
    gainers = service.get_coins(category="gainers", limit=5)
    assert all((c.get("price_change_percentage_24h") or 0.0) >= 0.0 for c in gainers["coins"])

    losers = service.get_coins(category="losers", limit=5)
    assert all((c.get("price_change_percentage_24h") or 0.0) <= 0.0 for c in losers["coins"])


def test_marketcap_api_endpoints() -> None:
    app = create_app()
    client = TestClient(app)

    # 1. Global
    res_global = client.get("/api/marketcap/global")
    assert res_global.status_code == 200
    data_global = res_global.json()
    assert "total_market_cap_usd" in data_global
    assert "btc_dominance_pct" in data_global

    # 2. Coins list
    res_coins = client.get("/api/marketcap/coins?limit=15&category=all")
    assert res_coins.status_code == 200
    data_coins = res_coins.json()
    assert "coins" in data_coins
    assert len(data_coins["coins"]) <= 15
    assert data_coins["total"] >= len(data_coins["coins"])

    # 3. Specific coin detail
    res_detail = client.get("/api/marketcap/coin/btc")
    assert res_detail.status_code == 200
    assert res_detail.json()["symbol"] == "BTC"

    # 4. Unknown coin 404
    res_unknown = client.get("/api/marketcap/coin/non_existent_token_xyz")
    assert res_unknown.status_code == 404
