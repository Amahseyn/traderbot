from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def unix_to_utc_iso(unix_seconds: int) -> str:
    return (
        datetime.fromtimestamp(int(unix_seconds), tz=timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def bar_close_unix(open_unix: int, bar_minutes: int) -> int:
    return int(open_unix) + int(bar_minutes) * 60


def fit_window_utc_from_bars(
    bars: list[dict[str, Any]],
    *,
    bar_minutes: int,
    holdout_tail_bars: int | None = None,
) -> tuple[str | None, str | None]:
    """UTC range where the optimizer actually fit (train bars, excluding internal holdout tail)."""
    if not bars or bar_minutes < 1:
        return None, None
    train = list(bars)
    if holdout_tail_bars is not None and holdout_tail_bars > 0 and len(train) > holdout_tail_bars:
        train = train[:-holdout_tail_bars]
    if not train:
        return None, None
    start = unix_to_utc_iso(int(train[0]["timestamp"]))
    end = unix_to_utc_iso(bar_close_unix(int(train[-1]["timestamp"]), bar_minutes))
    return start, end


def sample_window_utc_from_bars(
    bars: list[dict[str, Any]],
    *,
    bar_minutes: int,
) -> tuple[str | None, str | None]:
    if not bars or bar_minutes < 1:
        return None, None
    start = unix_to_utc_iso(int(bars[0]["timestamp"]))
    end = unix_to_utc_iso(bar_close_unix(int(bars[-1]["timestamp"]), bar_minutes))
    return start, end


def compare_window_utc_from_unix(
    start_unix_seconds: int | None,
    end_unix_seconds: int | None,
) -> tuple[str | None, str | None]:
    start = unix_to_utc_iso(start_unix_seconds) if start_unix_seconds is not None else None
    end = unix_to_utc_iso(end_unix_seconds) if end_unix_seconds is not None else None
    return start, end


def infer_bar_minutes(bars: list[dict[str, Any]], default: int = 60) -> int:
    if len(bars) < 2:
        return default
    delta = int(bars[1]["timestamp"]) - int(bars[0]["timestamp"])
    if delta <= 0:
        return default
    minutes = delta // 60
    return minutes if minutes >= 1 else default
