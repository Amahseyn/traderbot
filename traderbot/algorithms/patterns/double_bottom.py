from __future__ import annotations

from traderbot.algorithms.patterns.constants import (
    DEFAULT_LOW_TOLERANCE_RATIO,
    DEFAULT_MIN_SWING_SEPARATION_BARS,
    DEFAULT_NECKLINE_BREAK_BUFFER_RATIO,
    DEFAULT_SWING_WINDOW_BARS,
)
from traderbot.algorithms.patterns.swings import is_confirmed_swing_low


def _lows_similar(first_low: float, second_low: float, tolerance_ratio: float) -> bool:
    if first_low <= 0 or second_low <= 0:
        return False
    midpoint = (first_low + second_low) / 2.0
    return abs(first_low - second_low) / midpoint <= tolerance_ratio


def double_bottom_score(
    lows: list[float],
    highs: list[float],
    closes: list[float],
    *,
    swing_window_bars: int = DEFAULT_SWING_WINDOW_BARS,
    min_swing_separation_bars: int = DEFAULT_MIN_SWING_SEPARATION_BARS,
    low_tolerance_ratio: float = DEFAULT_LOW_TOLERANCE_RATIO,
    neckline_break_buffer_ratio: float = DEFAULT_NECKLINE_BREAK_BUFFER_RATIO,
    swing_low_indices: list[int] | None = None,
) -> float:
    """
    Soft score in [0, 1] for a completed double-bottom neckline break at the latest bar.
    Uses only bars through the latest index (causal).
    """
    bar_count = len(closes)
    if bar_count != len(lows) or bar_count != len(highs) or bar_count < 2 * swing_window_bars + 1:
        return 0.0

    if swing_low_indices is None:
        swing_low_indices = []
        for end_index in range(2 * swing_window_bars, bar_count):
            pivot = is_confirmed_swing_low(lows[: end_index + 1], swing_window_bars)
            if pivot is not None and (not swing_low_indices or pivot > swing_low_indices[-1]):
                swing_low_indices.append(pivot)

    if len(swing_low_indices) < 2:
        return 0.0

    first_index = swing_low_indices[-2]
    second_index = swing_low_indices[-1]
    if second_index - first_index < min_swing_separation_bars:
        return 0.0

    first_low = lows[first_index]
    second_low = lows[second_index]
    if not _lows_similar(first_low, second_low, low_tolerance_ratio):
        return 0.0

    neckline = max(highs[first_index : second_index + 1])
    close = closes[-1]
    break_level = neckline * (1.0 + neckline_break_buffer_ratio)
    if close <= break_level:
        return 0.0

    separation_score = min(1.0, (second_index - first_index) / float(min_swing_separation_bars * 2))
    similarity_score = 1.0 - abs(first_low - second_low) / ((first_low + second_low) / 2.0) / low_tolerance_ratio
    similarity_score = max(0.0, min(1.0, similarity_score))
    break_score = min(1.0, (close - break_level) / break_level / 0.01) if break_level > 0 else 0.0
    return max(0.0, min(1.0, 0.4 * similarity_score + 0.3 * separation_score + 0.3 * break_score))
