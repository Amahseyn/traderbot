"""Local OHLC cache that grows over time (multi-week 1m/5m research data).

Hyperliquid's ``candleSnapshot`` only serves the most recent ~5000 candles per interval
(~3.5 days of 1m, ~17 days of 5m). Re-running :func:`update_hyperliquid_cache` regularly
(e.g. daily via cron) appends new closed bars to ``<cache_dir>/hyperliquid/<COIN>_<res>.csv``
so history accumulates beyond that window. Public market data only; no keys.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any, Callable

DEFAULT_CACHE_DIR = Path("data/cache")
_FIELDS = ("timestamp", "open", "high", "low", "close", "volume", "symbol", "resolution")


def cache_path(cache_dir: Path, venue: str, coin: str, resolution: str) -> Path:
    return Path(cache_dir) / venue / f"{coin.upper()}_{resolution}.csv"


def read_cached_bars(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            rows.append({
                "timestamp": int(row["timestamp"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume") or 0.0),
                "symbol": row.get("symbol") or "",
                "resolution": row.get("resolution") or "",
            })
    return rows


def merge_bars(existing: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Union by open timestamp (newer fetch wins), oldest first."""
    by_ts = {int(bar["timestamp"]): bar for bar in existing}
    for bar in new:
        by_ts[int(bar["timestamp"])] = bar
    return [by_ts[ts] for ts in sorted(by_ts)]


def write_cached_bars(path: Path, bars: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for bar in bars:
            writer.writerow({key: bar.get(key, "") for key in _FIELDS})
    tmp.replace(path)


def find_gaps(bars: list[dict[str, Any]], bar_seconds: int) -> list[tuple[int, int]]:
    """(last_before_gap, first_after_gap) open timestamps where bars are missing."""
    gaps = []
    for previous, current in zip(bars, bars[1:]):
        if int(current["timestamp"]) - int(previous["timestamp"]) > bar_seconds:
            gaps.append((int(previous["timestamp"]), int(current["timestamp"])))
    return gaps


def update_hyperliquid_cache(
    coin: str,
    resolution: str,
    *,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    lookback_days: float = 30.0,
    fetch: Callable[..., list[dict[str, Any]]] | None = None,
    now: float | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    """Fetch closed bars since the cached tail (or ``lookback_days``) and merge them in."""
    from traderbot.hyperliquid.market_data import _bar_duration_seconds, fetch_hyperliquid_ohlc_range

    fetch = fetch or fetch_hyperliquid_ohlc_range
    path = cache_path(cache_dir, "hyperliquid", coin, resolution)
    existing = read_cached_bars(path)
    now_s = int(time.time() if now is None else now)
    bar_seconds = _bar_duration_seconds(resolution)
    start = int(existing[-1]["timestamp"]) + bar_seconds if existing else now_s - int(lookback_days * 86400)
    new = fetch(src=coin.lower(), resolution=resolution, history_from_unix_seconds=start, history_to_unix_seconds=now_s)
    merged = merge_bars(existing, new)
    if merged:
        write_cached_bars(path, merged)
    return path, merged
