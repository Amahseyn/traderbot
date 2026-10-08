from lab.auth_service import api_keys_create


def test_api_keys_create_never_returns_private_key(monkeypatch):
    monkeypatch.setattr(
        "lab.auth_service.create_api_key",
        lambda *_a, **_k: {
            "status": "ok",
            "key": {"key": "public"},
            "privateKey": "super-secret",
        },
    )
    monkeypatch.setattr("lab.auth_service.load_env_file", lambda: None)
    monkeypatch.setattr("lab.auth_service.token_from_env", lambda: "token")
    result = api_keys_create(name="x", totp="123456", write_env=True)
    assert result["privateKey"].startswith("<redacted")
