from __future__ import annotations

from typing import Any

from traderbot.utils.bars import bars_from_ohlc_rows, load_bars_csv, normalize_bar

__all__ = [
    "bars_from_ohlc_rows",
    "load_bars_csv",
    "normalize_bar",
    "price_context_kwargs_from_namespace",
]


def price_context_kwargs_from_namespace(args: Any) -> dict[str, Any]:
    """Shared recent-price / intrahour kwargs for mean-reversion-style strategies."""
    return {
        "context_bars": getattr(args, "context_bars", 0),
        "buy_min_recent_return": getattr(args, "buy_min_recent_return", -0.03),
        "sell_max_recent_return": getattr(args, "sell_max_recent_return", 0.03),
        "buy_min_fine_last_5m": getattr(args, "buy_min_fine_last_5m", None),
        "sell_max_fine_last_5m": getattr(args, "sell_max_fine_last_5m", None),
    }
