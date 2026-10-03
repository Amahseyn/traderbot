"""Shared helpers used across backtest, ML, and data loading.

Domain-specific facades: ``traderbot.utils.ml``, ``traderbot.utils.algorithms``.
Package-level mirrors: ``traderbot.ml.utils``, ``traderbot.algorithms.utils``.
"""

from traderbot.utils.bars import bars_from_ohlc_rows, load_bars_csv, normalize_bar
from traderbot.utils.constants import INTRAHOUR_FEATURE_KEYS
from traderbot.utils.equity import buy_hold_value, final_equity_from_curve
from traderbot.utils.series import lookup_value_at_or_before, point_at_or_after

__all__ = [
    "INTRAHOUR_FEATURE_KEYS",
    "bars_from_ohlc_rows",
    "buy_hold_value",
    "final_equity_from_curve",
    "load_bars_csv",
    "lookup_value_at_or_before",
    "normalize_bar",
    "point_at_or_after",
]
