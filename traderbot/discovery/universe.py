from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from traderbot.hyperliquid.market_data import (
    fetch_hyperliquid_ohlc_range,
    fetch_hyperliquid_perp_coins,
    hyperliquid_market_symbol,
    hyperliquid_perp_is_delisted,
)
from traderbot.markets.exchange import normalize_live_exchange


@dataclass(frozen=True, slots=True)
class UniverseFilters:
    min_mean_volume_quote: float = 0.0
    max_symbols: int = 24
    include_delisted: bool = False


@dataclass(frozen=True, slots=True)
class UniverseEntry:
    symbol_key: str
    market_symbol: str
    mean_volume_quote_24h: float | None
    bar_count_sample: int
    skipped_reason: str | None = None


def _mean_quote_volume_from_bars(bars: list[dict[str, Any]]) -> float:
    if not bars:
        return 0.0
    total = 0.0
    for bar in bars:
        volume = float(bar.get("volume") or 0)
        close = float(bar.get("close") or 0)
        total += volume * close
    return total / len(bars)


def discover_hyperliquid_perp_universe(
    *,
    symbols: list[str] | None = None,
    resolution: str = "60",
    filters: UniverseFilters | None = None,
    fetch_recent_bars: Callable[..., list[dict[str, Any]]] | None = None,
) -> list[UniverseEntry]:
    """Return tradable HL perp coins with optional liquidity proxy from recent hourly bars."""
    venue = normalize_live_exchange("hyperliquid")
    if venue != "hyperliquid":
        raise ValueError("v1 discovery universe supports hyperliquid only")
    config = filters or UniverseFilters()
    if symbols:
        candidates = [coin.strip().lower() for coin in symbols if coin.strip()]
    else:
        candidates = [name.lower() for name in fetch_hyperliquid_perp_coins(include_delisted=config.include_delisted)]

    loader = fetch_recent_bars or _default_recent_bars
    entries: list[UniverseEntry] = []
    for symbol_key in candidates:
        if hyperliquid_perp_is_delisted(symbol_key):
            entries.append(
                UniverseEntry(
                    symbol_key=symbol_key,
                    market_symbol=hyperliquid_market_symbol(symbol_key, "usdt"),
                    mean_volume_quote_24h=None,
                    bar_count_sample=0,
                    skipped_reason="delisted",
                ),
            )
            continue
        try:
            bars = loader(src=symbol_key, resolution=resolution)
        except Exception:  # noqa: BLE001 — skip bad markets
            entries.append(
                UniverseEntry(
                    symbol_key=symbol_key,
                    market_symbol=hyperliquid_market_symbol(symbol_key, "usdt"),
                    mean_volume_quote_24h=None,
                    bar_count_sample=0,
                    skipped_reason="fetch_failed",
                ),
            )
            continue
        mean_vol = _mean_quote_volume_from_bars(bars[-24:] if len(bars) >= 24 else bars)
        if config.min_mean_volume_quote > 0 and mean_vol < config.min_mean_volume_quote:
            entries.append(
                UniverseEntry(
                    symbol_key=symbol_key,
                    market_symbol=hyperliquid_market_symbol(symbol_key, "usdt"),
                    mean_volume_quote_24h=mean_vol,
                    bar_count_sample=len(bars),
                    skipped_reason="low_liquidity",
                ),
            )
            continue
        entries.append(
            UniverseEntry(
                symbol_key=symbol_key,
                market_symbol=hyperliquid_market_symbol(symbol_key, "usdt"),
                mean_volume_quote_24h=mean_vol,
                bar_count_sample=len(bars),
            ),
        )

    tradable = [entry for entry in entries if entry.skipped_reason is None]
    tradable.sort(key=lambda row: row.mean_volume_quote_24h or 0.0, reverse=True)
    if config.max_symbols > 0:
        tradable = tradable[: config.max_symbols]
    tradable_keys = {row.symbol_key for row in tradable}
    rejected = [entry for entry in entries if entry.symbol_key not in tradable_keys]
    return tradable + rejected


def _default_recent_bars(*, src: str, resolution: str) -> list[dict[str, Any]]:
    import time

    history_to_unix_seconds = int(time.time())
    history_from_unix_seconds = history_to_unix_seconds - 48 * 3600
    return fetch_hyperliquid_ohlc_range(
        src=src,
        resolution=resolution,
        history_from_unix_seconds=history_from_unix_seconds,
        history_to_unix_seconds=history_to_unix_seconds,
    )
