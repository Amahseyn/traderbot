import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import requests

from traderbot.client import BASE_URL, USER_AGENT

RESOLUTIONS = ("1", "5", "15", "30", "60", "180", "240", "360", "720", "D", "2D", "3D")
MAX_CANDLES = 500


def market_symbol(src: str, dst: str) -> str:
    """e.g. btc + rls -> BTCIRT, eth + usdt -> ETHUSDT (Nobitex UDF symbols)."""
    src = src.strip().upper()
    dst = dst.strip().lower()
    if dst in ("rls", "irt", "rial"):
        return f"{src}IRT"
    return f"{src}{dst.upper()}"


def fetch_ohlc_page(
    *,
    symbol: str,
    resolution: str,
    to_ts: int,
    from_ts: int | None = None,
    page: int = 1,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    if resolution not in RESOLUTIONS:
        raise ValueError(f"interval must be one of {RESOLUTIONS}")
    params: dict[str, Any] = {
        "symbol": symbol,
        "resolution": resolution,
        "to": to_ts,
        "page": page,
    }
    if from_ts is not None:
        params["from"] = from_ts
    http = session or requests
    response = http.get(
        f"{BASE_URL.rstrip('/')}/market/udf/history",
        params=params,
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    response.raise_for_status()
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
    for i, ts in enumerate(times):
        rows.append(
            {
                "symbol": symbol,
                "resolution": resolution,
                "timestamp": ts,
                "datetime_utc": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                "open": opens[i],
                "high": highs[i],
                "low": lows[i],
                "close": closes[i],
                "volume": volumes[i],
            }
        )
    return rows


def fetch_ohlc_range(
    *,
    symbol: str,
    resolution: str,
    from_ts: int,
    to_ts: int,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Fetch all candles in [from_ts, to_ts] (paginated, max 500 per page)."""
    all_rows: list[dict[str, Any]] = []
    page = 1
    while True:
        payload = fetch_ohlc_page(
            symbol=symbol,
            resolution=resolution,
            from_ts=from_ts,
            to_ts=to_ts,
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
        time.sleep(0.2)
    # API returns oldest-first or mixed; sort by time for CSV
    all_rows.sort(key=lambda r: r["timestamp"])
    return all_rows


def fetch_latest_closed_bar(
    *,
    symbol: str,
    resolution: str,
    session: requests.Session | None = None,
) -> dict[str, Any] | None:
    """Return the most recent fully closed candle (second-to-last row when API returns the open bar)."""
    to_ts = int(time.time())
    payload = fetch_ohlc_page(
        symbol=symbol,
        resolution=resolution,
        to_ts=to_ts,
        page=1,
        session=session,
    )
    rows = ohlc_rows(payload, symbol=symbol, resolution=resolution)
    if not rows:
        return None
    rows.sort(key=lambda r: r["timestamp"])
    if len(rows) >= 2:
        return rows[-2]
    return rows[-1]


def incremental_bar_source(
    *,
    symbol: str,
    resolution: str,
    session: requests.Session | None = None,
) -> Callable[[], dict[str, Any] | None]:
    """Callable that yields each closed bar once (for live ``AlgorithmTrader`` loops)."""
    last_ts: int | None = None

    def source() -> dict[str, Any] | None:
        nonlocal last_ts
        bar = fetch_latest_closed_bar(symbol=symbol, resolution=resolution, session=session)
        if bar is None:
            return None
        ts = int(bar["timestamp"])
        if last_ts is not None and ts <= last_ts:
            return None
        last_ts = ts
        return bar

    return source
