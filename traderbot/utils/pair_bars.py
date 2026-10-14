from __future__ import annotations

from typing import Any


def align_bars_by_timestamp(
    primary_bars: list[dict[str, Any]],
    hedge_bars: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return primary bars with ``hedge_close`` from hedge series at matching timestamps."""
    hedge_by_timestamp = {int(bar["timestamp"]): float(bar["close"]) for bar in hedge_bars}
    aligned: list[dict[str, Any]] = []
    for bar in primary_bars:
        timestamp = int(bar["timestamp"])
        hedge_close = hedge_by_timestamp.get(timestamp)
        if hedge_close is None:
            continue
        merged = dict(bar)
        merged["hedge_close"] = hedge_close
        aligned.append(merged)
    return aligned
