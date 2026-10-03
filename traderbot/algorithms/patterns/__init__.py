"""Causal chart-pattern detection (swing pivots, double top/bottom scores)."""

from traderbot.algorithms.patterns.chart_state import ChartPatternState
from traderbot.algorithms.patterns.constants import (
    DEFAULT_LOW_TOLERANCE_RATIO,
    DEFAULT_MIN_SWING_SEPARATION_BARS,
    DEFAULT_NECKLINE_BREAK_BUFFER_RATIO,
    DEFAULT_SWING_WINDOW_BARS,
)
from traderbot.algorithms.patterns.double_bottom import double_bottom_score
from traderbot.algorithms.patterns.double_top import double_top_score
from traderbot.algorithms.patterns.swings import is_confirmed_swing_high, is_confirmed_swing_low

__all__ = [
    "ChartPatternState",
    "DEFAULT_LOW_TOLERANCE_RATIO",
    "DEFAULT_MIN_SWING_SEPARATION_BARS",
    "DEFAULT_NECKLINE_BREAK_BUFFER_RATIO",
    "DEFAULT_SWING_WINDOW_BARS",
    "double_bottom_score",
    "double_top_score",
    "is_confirmed_swing_high",
    "is_confirmed_swing_low",
]
