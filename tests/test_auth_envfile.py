from pathlib import Path

from auth.envfile import upsert_env_vars
from auth.apikeys import redact_apikey_response


def test_upsert_env_vars(tmp_path: Path):
    path = tmp_path / ".env"
    path.write_text("FOO=1\n", encoding="utf-8")
    upsert_env_vars(path, {"NOBITEX_API_PUBLIC_KEY": "pub", "FOO": "2"})
    text = path.read_text(encoding="utf-8")
    assert "NOBITEX_API_PUBLIC_KEY=pub" in text
    assert "FOO=2" in text
    assert oct(path.stat().st_mode & 0o777) == oct(0o600)


def test_redact_apikey_response():
    out = redact_apikey_response({"status": "ok", "privateKey": "secret"})
    assert out["privateKey"].startswith("<redacted")
