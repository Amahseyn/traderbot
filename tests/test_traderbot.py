import pytest

from traderbot.nobitex.client import NobitexClient, NobitexClientError
from traderbot.nobitex.signing import sign_request


def test_signing_stable(keys):
    _, priv = keys
    a, _ = sign_request(private_key_b64=priv, method="GET", full_path="/users/profile", timestamp="1")
    b, _ = sign_request(private_key_b64=priv, method="GET", full_path="/users/profile", timestamp="1")
    assert a == b


def test_client_request(keys):
    pub, priv = keys

    def request_fn(method, url, headers=None, data=None, timeout=None):
        assert headers["Nobitex-Key"] == pub

        class R:
            status_code = 200

            def json(self):
                return {"status": "ok"}

        return R()

    NobitexClient(pub, priv, request_fn=request_fn).request("GET", "/users/profile")


def test_client_error(keys):
    pub, priv = keys

    def request_fn(*_a, **_k):
        class R:
            status_code = 401

            def json(self):
                return {}

        return R()

    with pytest.raises(NobitexClientError):
        NobitexClient(pub, priv, request_fn=request_fn).request("GET", "/users/profile")
