import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import requests

from traderbot.nobitex.client import BASE_URL, USER_AGENT
from traderbot.markets.http_client import http_get_with_retries
from traderbot.markets.utils import history_to_timestamp, trim_forming_candle
from traderbot.utils.bars import one_minute_bars_known_at, one_minute_history_to_timestamp
from traderbot.utils.constants import (
    NOBITEX_HTTP_TIMEOUT_SECONDS,
    NOBITEX_PAGE_DELAY_SECONDS,
    ONE_MINUTE_RESOLUTION,
)

RESOLUTIONS = ("1", "5", "15", "30", "60", "180", "240", "360", "720", "D", "2D", "3D")
MAX_CANDLES = 500


def market_symbol(src: str, dst: str) -> str:
    """e.g. btc + rls -> BTCIRT, eth + usdt -> ETHUSDT (Nobitex UDF symbols)."""
    src = src.strip().upper()
    dst = dst.strip().lower()
    if dst in ("rls", "irt", "rial"):
        return f"{src}IRT"
    return f"{src}{dst.upper()}"


def parse_nobitex_pair_key(pair_key: str) -> tuple[str, str]:
    """Nobitex ``market/stats`` key (e.g. ``btc-rls``, ``100k_floki-usdt``) → src, dst."""
    src_part, dst = pair_key.rsplit("-", 1)
    if dst not in ("rls", "usdt"):
        raise ValueError(f"unsupported Nobitex pair dst in {pair_key!r}")
    return src_part.lower(), dst


def fetch_nobitex_market_symbols(
    *,
    session: requests.Session | None = None,
) -> list[str]:
    """All tradable UDF symbols from Nobitex ``GET /market/stats`` (sorted, unique)."""
    response = http_get_with_retries(
        f"{BASE_URL.rstrip('/')}/market/stats",
        headers={"User-Agent": USER_AGENT},
        timeout=NOBITEX_HTTP_TIMEOUT_SECONDS,
        session=session,
    )
    payload = response.json()
    if payload.get("status") != "ok":
        raise ValueError("Nobitex market stats request failed")
    stats = payload.get("stats")
    if not isinstance(stats, dict):
        raise ValueError("Nobitex market stats response missing stats")
    symbols = {
        market_symbol(*parse_nobitex_pair_key(pair_key))
        for pair_key in stats
    }
    return sorted(symbols)


def fetch_ohlc_page(
    *,
    symbol: str,
    resolution: str,
    history_to_unix_seconds: int,
    history_from_unix_seconds: int | None = None,
    page = 1,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    if resolution not in RESOLUTIONS:
        raise ValueError(f"interval must be one of {RESOLUTIONS}")
    params: dict[str, Any] = {
        "symbol": symbol,
        "resolution": resolution,
        "to": history_to_unix_seconds,
        "page": page,
    }
    if history_from_unix_seconds is not None:
        params["from"] = history_from_unix_seconds
    response = http_get_with_retries(
        f"{BASE_URL.rstrip('/')}/market/udf/history",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=NOBITEX_HTTP_TIMEOUT_SECONDS,
        session=session,
    )
    return response.json()


def ohlc_rows(payload: dict[str, Any], *, symbol: str, resolution: str) -> list[dict[str, Any]]:
    if payload.get("s") != "ok":
        return []
    times = payload.get("t") or []
    opens = payload.get("o") or []
    highs = payload.get("h") or []
    lows = payload.get("l") or []
    closes = payload.get("c") or []
    volumes = payload.get("v") or []
    rows: list[dict[str, Any]] = []
    for bar_index, bar_open_unix_seconds in enumerate(times):
        rows.append(
            {
                "symbol": symbol,
                "resolution": resolution,
                "timestamp": bar_open_unix_seconds,
                "datetime_utc": datetime.fromtimestamp(bar_open_unix_seconds, tz=timezone.utc).isoformat(),
                "open": opens[bar_index],
                "high": highs[bar_index],
                "low": lows[bar_index],
                "close": closes[bar_index],
                "volume": volumes[bar_index],
            }
        )
    return rows


def fetch_ohlc_range(
    *,
    symbol: str,
    resolution: str,
    history_from_unix_seconds: int,
    history_to_unix_seconds: int,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Fetch all candles in [history_from_unix_seconds, history_to_unix_seconds] (paginated)."""
    all_rows: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = fetch_ohlc_page(
            symbol=symbol,
            resolution=resolution,
            history_from_unix_seconds=history_from_unix_seconds,
            history_to_unix_seconds=history_to_unix_seconds,
            page=page,
            session=session,
        )
        batch = ohlc_rows(payload, symbol=symbol, resolution=resolution)
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < MAX_CANDLES:
            break
        page += 1
        time.sleep(NOBITEX_PAGE_DELAY_SECONDS)
    all_rows.sort(key=lambda row: row["timestamp"])
    return all_rows


def fetch_latest_closed_bar(
    *,
    symbol: str,
    resolution: str,
    known_at_unix_seconds: int | None = None,
    session: requests.Session | None = None,
) -> dict[str, Any] | None:
    """Return the most recent fully closed candle (second-to-last row when API returns the open bar)."""
    history_to_unix_seconds = history_to_timestamp(resolution, known_at_unix_seconds)
    payload = fetch_ohlc_page(
        symbol=symbol,
        resolution=resolution,
        history_to_unix_seconds=history_to_unix_seconds,
        page=1,
        session=session,
    )
    rows = ohlc_rows(payload, symbol=symbol, resolution=resolution)
    if not rows:
        return None
    closed_bars = trim_forming_candle(rows)
    if not closed_bars:
        return None
    return closed_bars[-1]


def fetch_one_minute_bars(
    *,
    symbol: str,
    known_at_unix_seconds: int,
    max_bars: int = MAX_CANDLES,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Closed 1m OHLC for ``symbol`` at ``known_at_unix_seconds`` (oldest first, up to ``max_bars``)."""
    if max_bars < 1:
        return []
    history_to_unix_seconds = one_minute_history_to_timestamp(known_at_unix_seconds)
    payload = fetch_ohlc_page(
        symbol=symbol,
        resolution=ONE_MINUTE_RESOLUTION,
        history_to_unix_seconds=history_to_unix_seconds,
        page=1,
        session=session,
    )
    rows = ohlc_rows(payload, symbol=symbol, resolution=ONE_MINUTE_RESOLUTION)
    closed_bars = one_minute_bars_known_at(trim_forming_candle(rows), known_at_unix_seconds)
    return closed_bars[-max_bars:]


def fetch_recent_closed_bars(
    *,
    symbol: str,
    resolution: str,
    max_bars: int = MAX_CANDLES,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Closed OHLC history (oldest first), up to ``max_bars``."""
    if max_bars < 1:
        return []
    history_to_unix_seconds = history_to_timestamp(resolution, None)
    payload = fetch_ohlc_page(
        symbol=symbol,
        resolution=resolution,
        history_to_unix_seconds=history_to_unix_seconds,
        page=1,
        session=session,
    )
    rows = ohlc_rows(payload, symbol=symbol, resolution=resolution)
    closed_bars = trim_forming_candle(rows)
    return closed_bars[-max_bars:]


def incremental_bar_source(
    *,
    symbol: str,
    resolution: str,
    session: requests.Session | None = None,
    last_bar_open_unix_seconds: int | None = None,
) -> Callable[[], dict[str, Any] | None]:
    """Callable that yields each closed bar once (for live ``AlgorithmTrader`` loops)."""
    seen_last = last_bar_open_unix_seconds

    def source() -> dict[str, Any] | None:
        nonlocal seen_last
        bar = fetch_latest_closed_bar(symbol=symbol, resolution=resolution, session=session)
        if bar is None:
            return None
        bar_open_unix_seconds = int(bar["timestamp"])
        if seen_last is not None and bar_open_unix_seconds <= seen_last:
            return None
        seen_last = bar_open_unix_seconds
        return bar

    return source
