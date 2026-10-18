from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class _CacheEntry:
    expires_at: float
    payload: Any


class TtlCache:
    """Simple in-process TTL cache for CoinBeacon responses."""

    def __init__(self) -> None:
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            del self._entries[key]
            return None
        return entry.payload

    def set(self, key: str, payload: Any, ttl_seconds: float) -> None:
        self._entries[key] = _CacheEntry(
            expires_at=time.monotonic() + max(0.0, ttl_seconds),
            payload=payload,
        )

    def clear(self) -> None:
        self._entries.clear()


def cache_ttl_for_path(path: str) -> float:
    normalized = path.strip("/")
    if normalized == "public/screener/presets" or normalized == "public/screener/metrics":
        return 3600.0
    if normalized == "public/screener":
        return 75.0
    if normalized.startswith("public/trend-scanner"):
        return 45.0
    if normalized == "public/market/globals":
        return 600.0
    if normalized in ("public/market/sentiment", "public/market/structure"):
        return 60.0
    if normalized == "public/usage":
        return 30.0
    if normalized.startswith("public/funding/coin/"):
        return 120.0
    return 60.0
