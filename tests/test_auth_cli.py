import json

import pytest

from traderbot.cli.auth import main as auth_main


def test_auth_check_uses_client(monkeypatch, keys, capsys):
    pub, priv = keys
    monkeypatch.setenv("NOBITEX_API_PUBLIC_KEY", pub)
    monkeypatch.setenv("NOBITEX_API_PRIVATE_KEY", priv)

    def fake_request(self, method, path, **kwargs):
        assert method == "GET"
        assert path == "/users/profile"
        return {"status": "ok"}

    monkeypatch.setattr("traderbot.nobitex.client.NobitexClient.request", fake_request)
    auth_main(["check"])
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_auth_apikeys_list(monkeypatch, capsys):
    monkeypatch.setenv("NOBITEX_AUTH_TOKEN", "session-token")
    monkeypatch.setattr("traderbot.auth.envfile.load_env_file", lambda path=None: None)

    def fake_list(token):
        assert token == "session-token"
        return {"status": "ok", "keys": []}

    monkeypatch.setattr("traderbot.cli.auth.list_api_keys", fake_list)
    auth_main(["apikeys", "list"])
    out = json.loads(capsys.readouterr().out)
    assert out["keys"] == []


def test_auth_login_missing_username_non_tty(monkeypatch):
    monkeypatch.setattr("traderbot.cli.auth.sys.stdin", type("S", (), {"isatty": lambda self: False})())
    with pytest.raises(SystemExit) as exc:
        auth_main(["login"])
    assert exc.value.code == 2


def test_auth_login_prompts_totp(monkeypatch, capsys):
    monkeypatch.setattr("traderbot.cli.auth.sys.stdin", type("S", (), {"isatty": lambda self: True})())
    monkeypatch.setattr("traderbot.auth.envfile.load_env_file", lambda path=None: None)
    monkeypatch.setattr(
        "traderbot.cli.auth.getpass.getpass",
        lambda p: "123456" if "2FA" in p else "secret",
    )
    monkeypatch.setattr("traderbot.cli.auth._prompt_username", lambda: "user@example.com")
    monkeypatch.setattr(
        "traderbot.cli.auth.login_v2",
        lambda **kw: {"status": "success", "key": "tok", "expiresIn": 3600},
    )
    auth_main(["login", "--write-env"])
    captured = capsys.readouterr()
    assert "success" in captured.out
