"""Shared helpers for ML / forecast tests."""

from __future__ import annotations

import math


def synthetic_bars(
    n = 120,
    *,
    start = 100.0,
    bar_minutes = 60,
) -> list[dict]:
    bar_sec = bar_minutes * 60
    bars = []
    price = start
    for i in range(n):
        price *= 1.0 + 0.002 * math.sin(i / 7.0) + 0.0005 * (i % 5 - 2)
        bars.append(
            {
                "timestamp": 1_700_000_000 + i * bar_sec,
                "open": price * 0.999,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price,
                "volume": 1000.0 + i,
            }
        )
    return bars


def require_lightgbm():
    import pytest

    try:
        import lightgbm as lgb

        return lgb
    except (ImportError, OSError) as exc:
        pytest.skip(f"lightgbm unavailable: {exc}")
