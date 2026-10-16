from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from traderbot.hyperliquid.info_client import hyperliquid_info
from traderbot.markets.utils import trim_forming_candle
HYPERLIQUID_RESOLUTIONS = ("1", "5", "15", "30", "60", "240", "D")

_RESOLUTION_TO_INTERVAL: dict[str, str] = {
    "1": "1m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "240": "4h",
    "D": "1d",
}

_RESOLUTION_BAR_SECONDS: dict[str, int] = {
    "1": 60,
    "5": 5 * 60,
    "15": 15 * 60,
    "30": 30 * 60,
    "60": 60 * 60,
    "240": 4 * 60 * 60,
    "D": 24 * 60 * 60,
}

_INTERVAL_TO_RESOLUTION: dict[str, str] = {v: k for k, v in _RESOLUTION_TO_INTERVAL.items()}


def hyperliquid_resolution(interval_or_resolution: str) -> str:
    """Accept HL API resolution (``1``) or bar label (``1m``)."""
    s = str(interval_or_resolution).strip()
    if s in HYPERLIQUID_RESOLUTIONS:
        return s
    mapped = _INTERVAL_TO_RESOLUTION.get(s)
    if mapped is not None:
        return mapped
    raise ValueError(
        f"Hyperliquid resolution must be one of {HYPERLIQUID_RESOLUTIONS} "
        f"or {_INTERVAL_TO_RESOLUTION} (got {interval_or_resolution!r})"
    )


def hyperliquid_coin_from_src(src: str) -> str:
    """Perp coin name on Hyperliquid (e.g. btc → BTC)."""
    return src.strip().upper()


def hyperliquid_market_symbol(src: str, dst: str = "usdt") -> str:
    coin = hyperliquid_coin_from_src(src)
    quote = dst.strip().upper()
    if quote in ("USDT", "USDC", "USD"):
        return f"{coin}USDT"
    return f"{coin}{quote}"


def hyperliquid_interval(resolution: str) -> str:
    interval = _RESOLUTION_TO_INTERVAL.get(str(resolution))
    if interval is None:
        raise ValueError(
            f"Hyperliquid resolution must be one of {HYPERLIQUID_RESOLUTIONS} (got {resolution!r})"
        )
    return interval


def _bar_duration_seconds(resolution: str) -> int:
    seconds = _RESOLUTION_BAR_SECONDS.get(str(resolution))
    if seconds is None:
        raise ValueError(f"unsupported Hyperliquid resolution: {resolution!r}")
    return seconds


def _normalize_candle(candle: dict[str, Any], *, coin: str, resolution: str) -> dict[str, Any]:
    open_unix_seconds = int(int(candle["t"]) / 1000)
    return {
        "symbol": hyperliquid_market_symbol(coin.lower(), "usdt"),
        "resolution": str(resolution),
        "timestamp": open_unix_seconds,
        "open": float(candle["o"]),
        "high": float(candle["h"]),
        "low": float(candle["l"]),
        "close": float(candle["c"]),
        "volume": float(candle.get("v") or 0),
    }


def hyperliquid_perp_meta_entry(src: str) -> dict[str, Any] | None:
    coin = hyperliquid_coin_from_src(src)
    meta = hyperliquid_info().meta()
    universe = meta.get("universe")
    if not isinstance(universe, list):
        return None
    for entry in universe:
        if isinstance(entry, dict) and str(entry.get("name", "")).upper() == coin:
            return entry
    return None


def hyperliquid_perp_is_delisted(src: str) -> bool:
    entry = hyperliquid_perp_meta_entry(src)
    return bool(entry and entry.get("isDelisted"))


def hyperliquid_export_empty_reason(src: str, *, resolution: str) -> str:
    if hyperliquid_perp_is_delisted(src):
        return (
            f"{hyperliquid_coin_from_src(src)} is delisted on Hyperliquid "
            f"(isDelisted=true); no candle history is available — pick another market."
        )
    return (
        f"Hyperliquid returned 0 closed candles for {hyperliquid_coin_from_src(src)} "
        f"resolution {resolution} in the requested window."
    )


def fetch_hyperliquid_perp_coins(*, include_delisted: bool = False) -> list[str]:
    meta = hyperliquid_info().meta()
    universe = meta.get("universe")
    if not isinstance(universe, list):
        raise ValueError("Hyperliquid meta response missing universe")
    names: list[str] = []
    for entry in universe:
        if not isinstance(entry, dict) or not entry.get("name"):
            continue
        if not include_delisted and entry.get("isDelisted"):
            continue
        names.append(str(entry["name"]))
    return names


HYPERLIQUID_CANDLE_REQUEST_DELAY_SECONDS = 0.2


def fetch_hyperliquid_ohlc_range(
    *,
    src: str,
    resolution: str,
    history_from_unix_seconds: int,
    history_to_unix_seconds: int,
) -> list[dict[str, Any]]:
    """Paginated closed candles (oldest first) between two unix timestamps."""
    import time

    coin = hyperliquid_coin_from_src(src)
    interval = hyperliquid_interval(resolution)
    bar_seconds = _bar_duration_seconds(resolution)
    if history_to_unix_seconds <= history_from_unix_seconds:
        return []

    all_bars: list[dict[str, Any]] = []
    end_ms = int(history_to_unix_seconds) * 1000
    start_ms = int(history_from_unix_seconds) * 1000
    chunk_bars = 400
    chunk_ms = chunk_bars * bar_seconds * 1000
    cursor_end = end_ms

    while cursor_end > start_ms:
        cursor_start = max(start_ms, cursor_end - chunk_ms)
        candles = hyperliquid_info().candles_snapshot(coin, interval, cursor_start, cursor_end)
        if not candles:
            break
        batch = [_normalize_candle(row, coin=coin, resolution=resolution) for row in candles]
        all_bars.extend(batch)
        earliest_open_ms = int(candles[0]["t"])
        if earliest_open_ms <= start_ms:
            break
        cursor_end = earliest_open_ms - 1
        time.sleep(HYPERLIQUID_CANDLE_REQUEST_DELAY_SECONDS)

    all_bars.sort(key=lambda row: row["timestamp"])
    deduped: list[dict[str, Any]] = []
    seen: set[int] = set()
    for bar in all_bars:
        timestamp = int(bar["timestamp"])
        if timestamp in seen:
            continue
        seen.add(timestamp)
        deduped.append(bar)
    closed = trim_forming_candle(deduped)
    return [bar for bar in closed if history_from_unix_seconds <= int(bar["timestamp"]) <= history_to_unix_seconds]


def fetch_hyperliquid_recent_closed_bars(
    *,
    src: str,
    resolution: str,
    max_bars: int = 500,
) -> list[dict[str, Any]]:
    if max_bars < 1:
        return []
    coin = hyperliquid_coin_from_src(src)
    interval = hyperliquid_interval(resolution)
    bar_seconds = _bar_duration_seconds(resolution)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - (max_bars + 2) * bar_seconds * 1000
    candles = hyperliquid_info().candles_snapshot(coin, interval, start_ms, end_ms)
    if not candles:
        return []
    bars = [_normalize_candle(row, coin=coin, resolution=resolution) for row in candles]
    closed_bars = trim_forming_candle(bars)
    return closed_bars[-max_bars:]


def fetch_hyperliquid_closed_bars_after(
    *,
    src: str,
    resolution: str,
    after_open_unix_seconds: int,
) -> list[dict[str, Any]]:
    coin = hyperliquid_coin_from_src(src)
    interval = hyperliquid_interval(resolution)
    start_ms = (after_open_unix_seconds + 1) * 1000
    end_ms = int(time.time() * 1000)
    if start_ms >= end_ms:
        return []
    candles = hyperliquid_info().candles_snapshot(coin, interval, start_ms, end_ms)
    bars = [_normalize_candle(row, coin=coin, resolution=resolution) for row in candles or []]
    return trim_forming_candle(bars)


def hyperliquid_incremental_bar_source(
    *,
    src: str,
    resolution: str,
    last_bar_open_unix_seconds: int | None = None,
    pending_bars: list[dict[str, Any]] | None = None,
) -> Callable[[], dict[str, Any] | None]:
    coin = hyperliquid_coin_from_src(src)
    symbol = hyperliquid_market_symbol(src, "usdt")
    seen_last = last_bar_open_unix_seconds
    queue = list(pending_bars or [])

    def source() -> dict[str, Any] | None:
        nonlocal seen_last
        if queue:
            bar = queue.pop(0)
            seen_last = int(bar["timestamp"])
            return bar
        bars = fetch_hyperliquid_recent_closed_bars(src=src, resolution=resolution, max_bars=2)
        if not bars:
            return None
        bar = bars[-1]
        bar_open = int(bar["timestamp"])
        if seen_last is not None and bar_open <= seen_last:
            return None
        seen_last = bar_open
        bar = dict(bar)
        bar["symbol"] = symbol
        return bar

    return source
