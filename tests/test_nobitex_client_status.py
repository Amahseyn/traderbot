
from traderbot.nobitex.client import NobitexClient, NobitexClientError


def test_nobitex_client_rejects_failed_status_in_200(keys):
    pub, priv = keys

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "failed", "message": "nope"}

    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: FakeResponse())
    try:
        client.request("GET", "/users/profile")
    except NobitexClientError as exc:
        assert "rejected" in str(exc).lower()
    else:
        raise AssertionError("expected NobitexClientError")
