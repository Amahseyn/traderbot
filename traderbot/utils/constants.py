from __future__ import annotations

SECONDS_PER_MINUTE = 60
SECONDS_PER_DAY = 24 * 60 * SECONDS_PER_MINUTE

ONE_MINUTE_BAR_MINUTES = 1
ONE_MINUTE_RESOLUTION = "1"

INTRAHOUR_RETURN_5_MINUTE_BARS = 5
INTRAHOUR_RETURN_15_MINUTE_BARS = 15
INTRAHOUR_RETURN_60_MINUTE_BARS = 60

MIN_BAR_COUNT_TO_TRIM_FORMING_CANDLE = 2

NOBITEX_HTTP_TIMEOUT_SECONDS = 60
NOBITEX_PAGE_DELAY_SECONDS = 0.2

# Fast pytest / connectivity only — not enough bars for reliable strategy ranks.
CRYPTO_1H_SMOKE_TAIL_BARS = 24

INTRAHOUR_FEATURE_KEYS: tuple[str, ...] = (
    "fine_return_in_bar",
    "fine_return_last_5m",
    "fine_return_last_15m",
    "fine_return_last_60m",
)
