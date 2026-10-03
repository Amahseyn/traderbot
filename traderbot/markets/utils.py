from __future__ import annotations

import time
from typing import Any

from traderbot.ml.intervals import resolution_minutes
from traderbot.utils.constants import MIN_BAR_COUNT_TO_TRIM_FORMING_CANDLE, SECONDS_PER_MINUTE


def trim_forming_candle(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop the last row when a UDF page likely includes the still-open candle."""
    bars.sort(key=lambda bar: bar["timestamp"])
    if len(bars) >= MIN_BAR_COUNT_TO_TRIM_FORMING_CANDLE:
        return bars[:-1]
    return bars


def history_to_timestamp(resolution: str, known_at_unix_seconds: int | None) -> int:
    """Nobitex UDF ``to`` value: last closed bar before ``known_at_unix_seconds`` (any resolution)."""
    if known_at_unix_seconds is None:
        return int(time.time())
    bar_seconds = resolution_minutes(resolution) * SECONDS_PER_MINUTE
    return known_at_unix_seconds - bar_seconds
