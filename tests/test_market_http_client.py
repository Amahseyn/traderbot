import requests

from traderbot.markets.http_client import http_get_with_retries


def test_http_get_with_retries_recovers_from_ssl_error(monkeypatch):
    calls = {"count": 0}

    class FakeResponse:
        def raise_for_status(self):
            return None

    def fake_get(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] < 3:
            raise requests.exceptions.SSLError("simulated eof")
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)
    http_get_with_retries("https://example.test/stats", headers={}, timeout=1.0, attempts=4)
    assert calls["count"] == 3
