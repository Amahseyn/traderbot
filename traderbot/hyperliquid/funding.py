from __future__ import annotations

import time
from typing import Any

from traderbot.hyperliquid.info_client import hyperliquid_info
from traderbot.hyperliquid.market_data import hyperliquid_coin_from_src


def fetch_hyperliquid_funding_history(
    src: str,
    *,
    max_hours: int = 500,
) -> list[dict[str, Any]]:
    """Recent hourly funding events for a perp coin (public API, no keys)."""
    coin = hyperliquid_coin_from_src(src)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - max_hours * 3600 * 1000
    rows = hyperliquid_info().funding_history(coin, start_ms, end_ms) or []
    normalized: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(
            {
                "coin": str(row.get("coin") or coin),
                "funding_rate": float(row.get("fundingRate") or 0),
                "premium": float(row.get("premium") or 0),
                "time_unix_seconds": int(int(row["time"]) / 1000),
            }
        )
    return normalized
