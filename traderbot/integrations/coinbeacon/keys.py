from __future__ import annotations

import os


def load_coinbeacon_api_keys() -> list[str]:
    """Primary + alternates from env (never log or commit these values)."""
    keys: list[str] = []
    seen: set[str] = set()

    def add(raw: str | None) -> None:
        if not raw:
            return
        for part in raw.replace("\n", ",").split(","):
            key = part.strip()
            if key and key not in seen:
                seen.add(key)
                keys.append(key)

    add(os.environ.get("COINBEACON_API_KEY"))
    add(os.environ.get("COINBEACON_API_KEY_ALT"))
    add(os.environ.get("COINBEACON_API_KEYS"))

    return keys


def coinbeacon_api_key_configured() -> bool:
    return len(load_coinbeacon_api_keys()) > 0
