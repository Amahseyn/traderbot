from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from traderbot.hyperliquid.market_data import (
    HYPERLIQUID_RESOLUTIONS,
    fetch_hyperliquid_ohlc_range,
)
from traderbot.markets.exchange import normalize_live_exchange
from traderbot.markets.market_data import RESOLUTIONS as NOBITEX_RESOLUTIONS
from traderbot.markets.market_data import fetch_ohlc_range, market_symbol
from traderbot.markets.utils import trim_forming_candle

EVAL_RESOLUTIONS = ("1", "5", "15", "60", "240", "D")
DEFAULT_HISTORY_MONTHS = 6
CACHE_ROOT = Path("results/strategy_eval/cache")


def resolution_supported(exchange: str, resolution: str) -> bool:
    venue = normalize_live_exchange(exchange)
    if venue == "hyperliquid":
        return resolution in HYPERLIQUID_RESOLUTIONS
    return resolution in NOBITEX_RESOLUTIONS


def _cache_path(exchange: str, symbol_key: str, resolution: str) -> Path:
    safe = symbol_key.replace("/", "_")
    return CACHE_ROOT / exchange / f"{safe}_{resolution}.json"


def load_cached_bars(exchange: str, symbol_key: str, resolution: str) -> list[dict[str, Any]] | None:
    path = _cache_path(exchange, symbol_key, resolution)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("bars")


def save_cached_bars(
    exchange: str,
    symbol_key: str,
    resolution: str,
    bars: list[dict[str, Any]],
    *,
    meta: dict[str, Any] | None = None,
) -> Path:
    path = _cache_path(exchange, symbol_key, resolution)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "exchange": exchange,
                "symbol_key": symbol_key,
                "resolution": resolution,
                "bar_count": len(bars),
                "meta": meta or {},
                "bars": bars,
            },
            indent=0,
        ),
        encoding="utf-8",
    )
    return path


def fetch_history_bars(
    *,
    exchange: str,
    symbol_key: str,
    resolution: str,
    months: int = DEFAULT_HISTORY_MONTHS,
    use_cache: bool = True,
) -> list[dict[str, Any]]:
    if not resolution_supported(exchange, resolution):
        return []
    if use_cache:
        cached = load_cached_bars(exchange, symbol_key, resolution)
        if cached:
            return cached

    history_to_unix_seconds = int(time.time())
    history_from_unix_seconds = history_to_unix_seconds - int(months * 30.5 * 24 * 3600)
    venue = normalize_live_exchange(exchange)

    if venue == "hyperliquid":
        src = symbol_key.lower()
        bars = fetch_hyperliquid_ohlc_range(
            src=src,
            resolution=resolution,
            history_from_unix_seconds=history_from_unix_seconds,
            history_to_unix_seconds=history_to_unix_seconds,
        )
    else:
        symbol = symbol_key
        bars = fetch_ohlc_range(
            symbol=symbol,
            resolution=resolution,
            history_from_unix_seconds=history_from_unix_seconds,
            history_to_unix_seconds=history_to_unix_seconds,
        )
        bars = trim_forming_candle(bars)

    if bars and use_cache:
        save_cached_bars(
            exchange,
            symbol_key,
            resolution,
            bars,
            meta={
                "from_unix_seconds": history_from_unix_seconds,
                "to_unix_seconds": history_to_unix_seconds,
                "months": months,
            },
        )
    return bars


def nobitex_symbol(src: str, dst: str) -> str:
    return market_symbol(src, dst)
