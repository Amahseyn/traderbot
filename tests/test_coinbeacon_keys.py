from __future__ import annotations

import pytest

from traderbot.integrations.coinbeacon.client import CoinBeaconClient, CoinBeaconCredits
from traderbot.integrations.coinbeacon.keys import load_coinbeacon_api_keys


def test_load_coinbeacon_api_keys_primary_and_alt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COINBEACON_API_KEY", "key_a")
    monkeypatch.setenv("COINBEACON_API_KEY_ALT", "key_b")
    monkeypatch.delenv("COINBEACON_API_KEYS", raising=False)
    assert load_coinbeacon_api_keys() == ["key_a", "key_b"]


def test_load_coinbeacon_api_keys_list_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COINBEACON_API_KEY", raising=False)
    monkeypatch.delenv("COINBEACON_API_KEY_ALT", raising=False)
    monkeypatch.setenv("COINBEACON_API_KEYS", "key_x, key_y")
    assert load_coinbeacon_api_keys() == ["key_x", "key_y"]


def test_load_lab_repo_env_reads_dotenv(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import lab.store.constants as store_constants

    monkeypatch.setattr(store_constants, "REPO_ROOT", tmp_path)
    for name in ("COINBEACON_API_KEY", "COINBEACON_API_KEY_ALT", "COINBEACON_API_KEYS"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text("COINBEACON_API_KEYS=from_dotenv\n", encoding="utf-8")
    from lab.config import load_lab_repo_env

    load_lab_repo_env()
    assert load_coinbeacon_api_keys() == ["from_dotenv"]


def test_client_rotates_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    client = CoinBeaconClient(api_keys=["key_a", "key_b"], max_retries=0)
    calls: list[str] = []

    class FakeResponse:
        def __init__(self, status: int, payload: dict) -> None:
            self.status_code = status
            self._payload = payload
            self.text = ""

        @property
        def headers(self) -> dict[str, str]:
            return {"X-Credits-Remaining": "100"}

        def json(self) -> dict:
            return self._payload

    def fake_get(_url, headers=None, timeout=None) -> FakeResponse:
        key = headers["X-API-Key"]
        calls.append(key)
        if key == "key_a":
            return FakeResponse(429, {})
        return FakeResponse(200, {"ok": True})

    monkeypatch.setattr(client._session, "get", fake_get)
    payload = client.get_public("public/usage", use_cache=False)
    assert payload == {"ok": True}
    assert calls == ["key_a", "key_b"]
    assert client.active_key_index == 1


def test_rotate_if_credits_low() -> None:
    client = CoinBeaconClient(api_keys=["a", "b"])
    client.last_credits = CoinBeaconCredits(remaining=10)
    assert client.rotate_if_credits_low(50) is True
    assert client.active_key_index == 1
    assert client.rotate_if_credits_low(50) is False
