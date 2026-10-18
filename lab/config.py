from __future__ import annotations

import os


def load_lab_repo_env() -> None:
    """Load repo-root ``.env`` into the Lab API process (does not override existing env)."""
    from auth.envfile import load_env_file
    from lab.store.constants import REPO_ROOT

    load_env_file(REPO_ROOT / ".env")


def lab_api_host() -> str:
    return os.environ.get("LAB_API_HOST", "127.0.0.1").strip() or "127.0.0.1"


def lab_ui_origin() -> str:
    return os.environ.get("LAB_UI_ORIGIN", "http://127.0.0.1:3000").strip()


def lab_cors_origins() -> list[str]:
    raw = os.environ.get("LAB_CORS_ORIGINS", "").strip()
    if raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return [lab_ui_origin()]


def lab_api_auth_enabled() -> bool:
    disabled = os.environ.get("LAB_API_DISABLE_AUTH", "").strip().lower()
    return disabled not in ("1", "true", "yes")


def lab_api_max_body_bytes() -> int:
    raw = os.environ.get("LAB_API_MAX_BODY_BYTES", "2097152").strip()
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 2_097_152
    return max(1024, parsed)
