from __future__ import annotations

import os


def lab_api_host() -> str:
    return os.environ.get("LAB_API_HOST", "127.0.0.1").strip() or "127.0.0.1"


def lab_ui_origin() -> str:
    return os.environ.get("LAB_UI_ORIGIN", "http://127.0.0.1:3000").strip()


def lab_cors_origins() -> list[str]:
    raw = os.environ.get("LAB_CORS_ORIGINS", "").strip()
    if raw:
        return [part.strip() for part in raw.split(",") if part.strip()]
    return [lab_ui_origin()]
