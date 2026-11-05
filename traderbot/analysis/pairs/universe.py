from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from traderbot.analysis.pairs.models import MarketUniverseFilter
from traderbot.hyperliquid.market_data import (
    fetch_hyperliquid_perp_coins,
    hyperliquid_perp_is_delisted,
    hyperliquid_perp_meta_entry,
)
from traderbot.markets.exchange import normalize_live_exchange


@dataclass(frozen=True, slots=True)
class MarketMetadata:
    symbol: str
    exchange: str
    is_active: bool = True
    is_delisted: bool = False
    listing_unix_seconds: int | None = None
    delisting_unix_seconds: int | None = None
    bid_ask_spread_pct: float | None = None
    order_book_depth_usd: float | None = None
    volume_quote_24h: float | None = None


def validate_ohlcv_bars(bars: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """
    Ensure OHLCV bars are causal, valid, and free of anomalies or corruption.
    """
    if not bars:
        return False, "empty_bars"

    previous_timestamp = -1
    for index, bar in enumerate(bars):
        timestamp = bar.get("timestamp")
        open_p = bar.get("open")
        high_p = bar.get("high")
        low_p = bar.get("low")
        close_p = bar.get("close")
        volume = bar.get("volume")

        # 1. Null / Non-finite checks
        for key, val in (("timestamp", timestamp), ("open", open_p), ("high", high_p), ("low", low_p), ("close", close_p)):
            if val is None or not math.isfinite(float(val)):
                return False, f"invalid_finite_value_{key}_at_index_{index}"

        ts = int(timestamp)
        o = float(open_p)
        h = float(high_p)
        l = float(low_p)
        c = float(close_p)
        v = float(volume) if volume is not None and math.isfinite(float(volume)) else 0.0

        # 2. Strict positive price check
        if o <= 0 or h <= 0 or l <= 0 or c <= 0 or v < 0:
            return False, f"non_positive_price_or_negative_volume_at_index_{index}"

        # 3. Bar integrity: high >= low, high >= max(open, close), low <= min(open, close)
        if h < l or h < o or h < c or l > o or l > c:
            return False, f"corrupt_high_low_envelope_at_index_{index}"

        # 4. Strict monotonic chronological order
        if ts <= previous_timestamp:
            return False, f"non_monotonic_timestamp_at_index_{index}"
        previous_timestamp = ts

    return True, None


def compute_24h_quote_volume(bars: list[dict[str, Any]], resolution: str = "60") -> float:
    """Calculate rolling 24h quote volume from the tail of closed bars."""
    if not bars:
        return 0.0
    # Determine how many bars represent 24h
    step_minutes = int(resolution) if resolution.isdigit() else 60
    bars_in_24h = max(1, (24 * 60) // step_minutes)
    sample = bars[-bars_in_24h:] if len(bars) >= bars_in_24h else bars

    total = 0.0
    for bar in sample:
        v = float(bar.get("volume") or 0.0)
        c = float(bar.get("close") or 0.0)
        total += v * c
    return total


def filter_market(
    symbol: str,
    bars: list[dict[str, Any]],
    metadata: MarketMetadata | None,
    filter_config: MarketUniverseFilter,
    *,
    as_of_unix_seconds: int | None = None,
    resolution: str = "60",
) -> tuple[bool, list[str]]:
    """
    Evaluate single market eligibility against institutional filtering rules.
    Operates strictly point-in-time when as_of_unix_seconds is provided.
    """
    reasons: list[str] = []

    # 1. Point-in-time causal slicing
    if as_of_unix_seconds is not None:
        causal_bars = [b for b in bars if int(b.get("timestamp", 0)) <= as_of_unix_seconds]
    else:
        causal_bars = bars

    # 2. History length check
    if len(causal_bars) < filter_config.min_history_bars:
        reasons.append(
            f"insufficient_history ({len(causal_bars)} < {filter_config.min_history_bars})"
        )

    # 3. OHLCV integrity check
    if causal_bars:
        is_valid, validation_error = validate_ohlcv_bars(causal_bars)
        if not is_valid:
            reasons.append(f"invalid_ohlcv ({validation_error})")

    # 4. Metadata filters (delisted, inactive, spread, depth)
    if metadata is not None:
        # Delisted check
        if filter_config.filter_delisted:
            if metadata.is_delisted:
                # If point-in-time, check if delisting was before as_of_unix_seconds
                if metadata.delisting_unix_seconds is not None and as_of_unix_seconds is not None:
                    if metadata.delisting_unix_seconds <= as_of_unix_seconds:
                        reasons.append("delisted_market")
                else:
                    reasons.append("delisted_market")

        # Listing check (Point-in-Time: cannot trade an asset before its listing timestamp)
        if metadata.listing_unix_seconds is not None and as_of_unix_seconds is not None:
            if metadata.listing_unix_seconds > as_of_unix_seconds:
                reasons.append("unlisted_at_decision_time")

        # Inactive check
        if filter_config.filter_inactive and not metadata.is_active:
            reasons.append("inactive_market")

        # Bid-ask spread check
        if metadata.bid_ask_spread_pct is not None:
            if metadata.bid_ask_spread_pct > filter_config.max_bid_ask_spread_pct:
                reasons.append(
                    f"excessive_spread ({metadata.bid_ask_spread_pct * 100:.3f}% > {filter_config.max_bid_ask_spread_pct * 100:.3f}%)"
                )

        # Order book depth check
        if metadata.order_book_depth_usd is not None:
            if metadata.order_book_depth_usd < filter_config.min_order_book_depth_usd:
                reasons.append(
                    f"insufficient_depth (${metadata.order_book_depth_usd:,.0f} < ${filter_config.min_order_book_depth_usd:,.0f})"
                )

    # 5. Volume check (calculated point-in-time from causal bars)
    vol_24h = compute_24h_quote_volume(causal_bars, resolution=resolution)
    if vol_24h < filter_config.min_volume_quote_24h:
        reasons.append(
            f"low_volume (${vol_24h:,.0f} < ${filter_config.min_volume_quote_24h:,.0f})"
        )

    is_eligible = len(reasons) == 0
    return is_eligible, reasons


def discover_tradable_universe(
    exchange: str,
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    metadata_by_symbol: dict[str, MarketMetadata] | None = None,
    filter_config: MarketUniverseFilter | None = None,
    *,
    as_of_unix_seconds: int | None = None,
    resolution: str = "60",
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[str]]]:
    """
    Filter input multi-asset bars down to an institutional tradable universe.
    Returns:
        (tradable_bars_by_symbol, rejected_symbols_with_reasons)
    """
    venue = normalize_live_exchange(exchange)
    config = filter_config or MarketUniverseFilter()
    meta_map = metadata_by_symbol or {}

    tradable: dict[str, list[dict[str, Any]]] = {}
    rejected: dict[str, list[str]] = {}

    # Sort symbols for determinism
    symbols = sorted(bars_by_symbol.keys())
    for symbol in symbols:
        raw_bars = bars_by_symbol[symbol]
        meta = meta_map.get(symbol)
        eligible, reasons = filter_market(
            symbol,
            raw_bars,
            meta,
            config,
            as_of_unix_seconds=as_of_unix_seconds,
            resolution=resolution,
        )
        if eligible:
            # Strictly slice bars causally
            if as_of_unix_seconds is not None:
                sliced = [b for b in raw_bars if int(b.get("timestamp", 0)) <= as_of_unix_seconds]
            else:
                sliced = raw_bars
            tradable[symbol] = sliced
        else:
            rejected[symbol] = reasons

    # If universe size exceeds max_symbols, rank eligible by 24h volume
    if config.max_symbols > 0 and len(tradable) > config.max_symbols:
        sorted_by_vol = sorted(
            tradable.keys(),
            key=lambda sym: compute_24h_quote_volume(tradable[sym], resolution=resolution),
            reverse=True,
        )
        kept_symbols = set(sorted_by_vol[: config.max_symbols])
        for sym in list(tradable.keys()):
            if sym not in kept_symbols:
                rejected[sym] = [f"universe_capacity_limit (max {config.max_symbols})"]
                del tradable[sym]

    return tradable, rejected

