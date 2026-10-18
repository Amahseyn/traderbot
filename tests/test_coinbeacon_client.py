from __future__ import annotations

import json
from pathlib import Path

import pytest

from traderbot.integrations.coinbeacon.client import CoinBeaconClient, credits_from_headers


def test_credits_from_headers() -> None:
    credits = credits_from_headers(
        {
            "X-Credits-Cost": "5",
            "X-Credits-Remaining": "1990",
            "X-Credits-Limit": "2000",
        },
    )
    assert credits.cost == 5
    assert credits.remaining == 1990


def test_get_public_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = Path(__file__).parent / "fixtures" / "coinbeacon" / "globals.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    calls = {"count": 0}

    class FakeResponse:
        status_code = 200
        text = "{}"

        def __init__(self) -> None:
            calls["count"] += 1

        @property
        def headers(self) -> dict[str, str]:
            return {"X-Credits-Cost": "1", "X-Credits-Remaining": "1999"}

        def json(self) -> dict:
            return payload

    def fake_get(*_args, **_kwargs) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setenv("COINBEACON_API_KEY", "cb_test_key")
    client = CoinBeaconClient()
    monkeypatch.setattr(client._session, "get", fake_get)

    first = client.get_public("public/market/globals")
    second = client.get_public("public/market/globals")
    assert first == payload
    assert second == payload
    assert calls["count"] == 1
