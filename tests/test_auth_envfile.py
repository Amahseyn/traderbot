from pathlib import Path

from traderbot.auth.envfile import upsert_env_vars
from traderbot.cli.auth import _redact_apikey_response


def test_upsert_env_vars(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text("FOO=1\n", encoding="utf-8")
    upsert_env_vars(path, {"NOBITEX_API_PUBLIC_KEY": "pub", "FOO": "2"})
    text = path.read_text(encoding="utf-8")
    assert "NOBITEX_API_PUBLIC_KEY=pub" in text
    assert "FOO=2" in text


def test_redact_apikey_response():
    out = _redact_apikey_response({"status": "ok", "privateKey": "secret"})
    assert out["privateKey"].startswith("<redacted")
