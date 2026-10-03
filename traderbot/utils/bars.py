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
