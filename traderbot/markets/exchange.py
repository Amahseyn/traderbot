from __future__ import annotations

import os
from typing import Any

from traderbot.hyperliquid.market_data import (
    HYPERLIQUID_RESOLUTIONS,
    fetch_hyperliquid_closed_bars_after,
    fetch_hyperliquid_recent_closed_bars,
    hyperliquid_incremental_bar_source,
    hyperliquid_market_symbol,
)
from traderbot.markets.market_data import (
    RESOLUTIONS as NOBITEX_RESOLUTIONS,
    fetch_closed_bars_after as fetch_nobitex_closed_bars_after,
    fetch_recent_closed_bars as fetch_nobitex_recent_closed_bars,
    incremental_bar_source as nobitex_incremental_bar_source,
    market_symbol as nobitex_market_symbol,
)

LIVE_EXCHANGES = ("hyperliquid", "nobitex")
DEFAULT_LIVE_EXCHANGE = "hyperliquid"


def exchange_for_catalog_scope(catalog_scope: str | None) -> str:
    """Map Lab ``market_catalog.catalog_scope`` to a live data venue."""
    scope = (catalog_scope or "").strip().lower()
    if scope == "hyperliquid_all":
        return "hyperliquid"
    return "nobitex"


def normalize_live_exchange(exchange: str | None) -> str:
    raw = (exchange or os.environ.get("TRADERBOT_LIVE_EXCHANGE") or DEFAULT_LIVE_EXCHANGE).strip().lower()
    if raw not in LIVE_EXCHANGES:
        raise ValueError(f"exchange must be one of {LIVE_EXCHANGES} (got {raw!r})")
    return raw


def live_resolutions(exchange: str) -> tuple[str, ...]:
    if normalize_live_exchange(exchange) == "hyperliquid":
        return HYPERLIQUID_RESOLUTIONS
    return NOBITEX_RESOLUTIONS


def live_market_symbol(exchange: str, src: str, dst: str) -> str:
    if normalize_live_exchange(exchange) == "hyperliquid":
        return hyperliquid_market_symbol(src, dst)
    return nobitex_market_symbol(src, dst)


def fetch_live_recent_closed_bars(
    *,
    exchange: str,
    src: str,
    dst: str,
    resolution: str,
    max_bars: int = 500,
) -> list[dict[str, Any]]:
    if normalize_live_exchange(exchange) == "hyperliquid":
        return fetch_hyperliquid_recent_closed_bars(src=src, resolution=resolution, max_bars=max_bars)
    symbol = nobitex_market_symbol(src, dst)
    return fetch_nobitex_recent_closed_bars(symbol=symbol, resolution=resolution, max_bars=max_bars)


def fetch_live_closed_bars_after(
    *,
    exchange: str,
    src: str,
    dst: str,
    resolution: str,
    after_open_unix_seconds: int,
) -> list[dict[str, Any]]:
    if normalize_live_exchange(exchange) == "hyperliquid":
        return fetch_hyperliquid_closed_bars_after(
            src=src,
            resolution=resolution,
            after_open_unix_seconds=after_open_unix_seconds,
        )
    symbol = nobitex_market_symbol(src, dst)
    return fetch_nobitex_closed_bars_after(
        symbol=symbol,
        resolution=resolution,
        after_open_unix_seconds=after_open_unix_seconds,
    )


def live_incremental_bar_source(
    *,
    exchange: str,
    src: str,
    dst: str,
    resolution: str,
    last_bar_open_unix_seconds: int | None = None,
    pending_bars: list[dict[str, Any]] | None = None,
    use_websocket: bool = False,
):
    if normalize_live_exchange(exchange) == "hyperliquid":
        stream = None
        if use_websocket:
            from traderbot.hyperliquid.market_data import hyperliquid_candle_stream

            stream = hyperliquid_candle_stream(src=src, resolution=resolution)
        return hyperliquid_incremental_bar_source(
            src=src,
            resolution=resolution,
            last_bar_open_unix_seconds=last_bar_open_unix_seconds,
            pending_bars=pending_bars,
            stream=stream,
        )
    symbol = nobitex_market_symbol(src, dst)
    return nobitex_incremental_bar_source(
        symbol=symbol,
        resolution=resolution,
        last_bar_open_unix_seconds=last_bar_open_unix_seconds,
        pending_bars=pending_bars,
    )
