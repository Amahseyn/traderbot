

from lab.auth_service import api_keys_list, fetch_profile, login_session


def test_auth_profile_uses_client(monkeypatch, keys):
    pub, priv = keys
    monkeypatch.setenv("NOBITEX_API_PUBLIC_KEY", pub)
    monkeypatch.setenv("NOBITEX_API_PRIVATE_KEY", priv)

    def fake_request(self, method, path, **kwargs):
        assert method == "GET"
        assert path == "/users/profile"
        return {"status": "ok"}

    monkeypatch.setattr("traderbot.nobitex.client.NobitexClient.request", fake_request)
    assert fetch_profile()["status"] == "ok"


def test_auth_apikeys_list(monkeypatch):
    monkeypatch.setenv("NOBITEX_AUTH_TOKEN", "session-token")
    monkeypatch.setattr("auth.envfile.load_env_file", lambda path=None: None)

    def fake_list(token):
        assert token == "session-token"
        return [{"name": "k1"}]

    monkeypatch.setattr("lab.auth_service.list_api_keys", fake_list)
    assert api_keys_list() == [{"name": "k1"}]


def test_login_session_success(monkeypatch):
    monkeypatch.setattr("auth.envfile.load_env_file", lambda path=None: None)
    monkeypatch.setattr(
        "lab.auth_service.login_v2",
        lambda **kw: {"status": "success", "key": "tok", "expiresIn": 3600},
    )
    out = login_session(username="user@example.com", password="secret", totp="123456")
    assert out["ok"] is True
    assert out["status"] == "success"
