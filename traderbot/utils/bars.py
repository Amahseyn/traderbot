from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from traderbot.utils.constants import ONE_MINUTE_BAR_MINUTES, SECONDS_PER_MINUTE

_NUMERIC_BAR_KEYS = ("open", "high", "low", "close", "volume")


def normalize_bar(row: dict[str, Any]) -> dict[str, Any]:
    """Coerce OHLC fields to float; keeps export CSV / :mod:`market_data` shape."""
    out = dict(row)
    if "timestamp" in out:
        out["timestamp"] = int(out["timestamp"])
    for key in _NUMERIC_BAR_KEYS:
        if key in out and out[key] != "":
            out[key] = float(out[key])
    return out


def bars_last_n(bars: list[dict[str, Any]], bar_count: int) -> list[dict[str, Any]]:
    """Keep only the most recent ``bar_count`` candles (oldest-first order preserved)."""
    if bar_count < 1 or len(bars) <= bar_count:
        return list(bars)
    return list(bars[-bar_count:])


def filter_bars_by_unix_range(
    bars: list[dict[str, Any]],
    *,
    start_unix_seconds: int | None = None,
    end_unix_seconds: int | None = None,
    bar_minutes: int,
) -> list[dict[str, Any]]:
    """
    Subset OHLC rows by bar open time and close time (no partial bar past ``end``).

    ``timestamp`` is bar open (export CSV shape). A bar is included when its open is
    at or after ``start_unix_seconds`` (if set) and its close is at or before
    ``end_unix_seconds`` (if set).
    """
    if start_unix_seconds is None and end_unix_seconds is None:
        return list(bars)
    if bar_minutes < 1:
        raise ValueError("bar_minutes must be >= 1")
    bar_seconds = bar_minutes * SECONDS_PER_MINUTE
    filtered: list[dict[str, Any]] = []
    for bar in bars:
        open_unix_seconds = int(bar["timestamp"])
        if start_unix_seconds is not None and open_unix_seconds < start_unix_seconds:
            continue
        if end_unix_seconds is not None and open_unix_seconds + bar_seconds > end_unix_seconds:
            continue
        filtered.append(bar)
    return filtered


def load_bars_csv(path: Path) -> list[dict[str, Any]]:
    """Load candles written by :func:`traderbot.data.export.write_csv`."""
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        rows = [normalize_bar(row) for row in reader]
    rows.sort(key=lambda r: r["timestamp"])
    return rows


def bars_from_ohlc_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure bar list matches backtest expectations (sorted, numeric OHLC)."""
    normalized = [normalize_bar(r) for r in rows]
    normalized.sort(key=lambda r: r["timestamp"])
    return normalized


def one_minute_bar_seconds(*, bar_minutes: int = ONE_MINUTE_BAR_MINUTES) -> int:
    return bar_minutes * SECONDS_PER_MINUTE


def one_minute_history_to_timestamp(
    known_at_unix_seconds: int,
    *,
    bar_minutes: int = ONE_MINUTE_BAR_MINUTES,
) -> int:
    """``to`` argument for Nobitex OHLC history: last closed 1m bar before ``known_at_unix_seconds``."""
    return known_at_unix_seconds - one_minute_bar_seconds(bar_minutes=bar_minutes)


def one_minute_bars_known_at(
    bars: list[dict[str, Any]],
    known_at_unix_seconds: int,
    *,
    bar_minutes: int = ONE_MINUTE_BAR_MINUTES,
) -> list[dict[str, Any]]:
    """1m bars fully closed when the clock reads ``known_at_unix_seconds`` (no lookahead)."""
    bar_seconds = one_minute_bar_seconds(bar_minutes=bar_minutes)
    return [b for b in bars if int(b["timestamp"]) + bar_seconds <= known_at_unix_seconds]
