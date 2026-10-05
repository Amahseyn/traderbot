from __future__ import annotations

from typing import Any

from traderbot.utils.constants import INTRAHOUR_FEATURE_KEYS
from traderbot.utils.equity import buy_hold_value, final_equity_from_curve
from utils.series import lookup_value_at_or_before, point_at_or_after

__all__ = [
    "INTRAHOUR_BAR_KEYS",
    "buy_hold_value",
    "final_equity_from_curve",
    "horizon_label",
    "lookup_value_at_or_before",
    "point_at_or_after",
    "price_series_from_bars",
]


INTRAHOUR_BAR_KEYS = INTRAHOUR_FEATURE_KEYS


def horizon_label(bar_minutes: int, horizon_bars: int) -> str:
    """Human label such as ``4h`` when bars are 60-minute."""
    minutes = bar_minutes * horizon_bars
    if minutes % (24 * 60) == 0:
        days = minutes // (24 * 60)
        return f"{days}d"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes}m"


def price_series_from_bars(bars: list[dict[str, Any]]) -> list[tuple[int, float]]:
    return [(int(b["timestamp"]), float(b["close"])) for b in bars]
