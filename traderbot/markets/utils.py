from __future__ import annotations

import time
from typing import Any

from traderbot.utils.resolution import resolution_minutes
from traderbot.utils.constants import MIN_BAR_COUNT_TO_TRIM_FORMING_CANDLE, SECONDS_PER_MINUTE

SECONDS_PER_DAY = 24 * 60 * 60


def trim_forming_candle(
    bars: list[dict[str, Any]],
    *,
    bar_seconds: int | None = None,
    now_unix_seconds: float | None = None,
) -> list[dict[str, Any]]:
    """Drop candles that are still forming.

    With ``bar_seconds`` the check is time-based (keep bars whose ``open + bar_seconds`` is
    not after ``now``), so a page that ends on a closed bar keeps it. Without it, the legacy
    heuristic drops the last row whenever there are at least two.
    """
    bars.sort(key=lambda bar: bar["timestamp"])
    if bar_seconds is not None:
        now = time.time() if now_unix_seconds is None else float(now_unix_seconds)
        return [bar for bar in bars if int(bar["timestamp"]) + int(bar_seconds) <= now]
    if len(bars) >= MIN_BAR_COUNT_TO_TRIM_FORMING_CANDLE:
        return bars[:-1]
    return bars


def resolution_seconds(resolution: str) -> int:
    return int(resolution_minutes(resolution) * SECONDS_PER_MINUTE)


def history_to_timestamp(resolution: str, known_at_unix_seconds: int | None) -> int:
    """Nobitex UDF ``to`` value that returns exactly the bars closed at ``known_at``.

    Checked against the public API (``/market/udf/history``, BTCIRT 1m, 2026-10-18): the
    response holds bars whose **open time is strictly before** ``to``, and ``to=now`` includes
    the still-forming candle. So ``to`` = the start of the current bar returns every closed bar
    and no forming one. The previous ``known_at - bar_seconds`` dropped the last closed bar
    (and, combined with trimming the last row, lagged by two bars).
    """
    now = int(time.time()) if known_at_unix_seconds is None else int(known_at_unix_seconds)
    bar_seconds = resolution_seconds(resolution)
    if bar_seconds >= SECONDS_PER_DAY:
        # Daily bar boundaries are venue-defined; keep ``now`` and filter by time instead.
        return now
    return now - now % bar_seconds
