from __future__ import annotations

from collections.abc import Sequence


def lookup_value_at_or_before(series: Sequence[tuple[int, float]], unix_seconds: int) -> float | None:
    """Last ``(timestamp, value)`` pair with timestamp ``<= unix_seconds`` (series must be time-sorted)."""
    value: float | None = None
    for point_unix_seconds, point_value in series:
        if point_unix_seconds > unix_seconds:
            break
        value = point_value
    return value


def point_at_or_after[T](points: Sequence[T], unix_seconds: int, *, index: int = 0) -> T | None:
    """First point whose element at ``index`` is ``>= unix_seconds``."""
    for point in points:
        if point[index] >= unix_seconds:
            return point
    return None
