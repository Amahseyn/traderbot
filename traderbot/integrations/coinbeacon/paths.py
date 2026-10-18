"""CoinBeacon /public route paths (see https://coinbeacon.io/docs/api)."""

from __future__ import annotations

COINBEACON_BASE_URL = "https://api.coinbeacon.io"

DEFAULT_SCREENER_PRESETS: tuple[str, ...] = (
    "oversold-4h",
    "deeply-oversold-4h",
    "overbought-4h",
    "volume-surge",
    "volume-10x",
    "capitulation",
    "near-ath",
    "deep-drawdown",
    "funding-expensive-longs",
    "funding-negative",
    "fresh-momentum",
    "squeeze",
    "new-listings",
    "golden-cross-1d",
    "high-turnover",
)

DEFAULT_TREND_EXCHANGE = "binance-futures"
DEFAULT_TREND_SORT = "1d"
DEFAULT_TREND_QUOTE = "USDT"

TREND_EXCHANGES: tuple[str, ...] = (
    "binance",
    "binance-futures",
    "bybit-futures",
    "okx-futures",
    "gateio-futures",
    "htx-futures",
)

TREND_SORT_TIMEFRAMES: tuple[str, ...] = ("15m", "1h", "4h", "1d", "1w")
