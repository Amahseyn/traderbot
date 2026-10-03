from __future__ import annotations

from collections.abc import Sequence


def lookup_value_at_or_before(series: Sequence[tuple[int, float]], ts: int) -> float | None:
    """Last ``(timestamp, value)`` pair with timestamp ``<= ts`` (series must be time-sorted)."""
    value: float | None = None
    for point_ts, point_val in series:
        if point_ts > ts:
            break
        value = point_val
    return value


def point_at_or_after[T](points: Sequence[T], ts: int, *, index: int = 0) -> T | None:
    """First point whose element at ``index`` is ``>= ts``."""
    for row in points:
        if row[index] >= ts:
            return row
    return None
