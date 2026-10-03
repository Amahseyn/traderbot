from __future__ import annotations

from traderbot.algorithms.patterns.constants import (
    DEFAULT_LOW_TOLERANCE_RATIO,
    DEFAULT_MIN_SWING_SEPARATION_BARS,
    DEFAULT_NECKLINE_BREAK_BUFFER_RATIO,
    DEFAULT_SWING_WINDOW_BARS,
)
from traderbot.algorithms.patterns.swings import is_confirmed_swing_high


def double_top_score(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    swing_window_bars: int = DEFAULT_SWING_WINDOW_BARS,
    min_swing_separation_bars: int = DEFAULT_MIN_SWING_SEPARATION_BARS,
    high_tolerance_ratio: float = DEFAULT_LOW_TOLERANCE_RATIO,
    neckline_break_buffer_ratio: float = DEFAULT_NECKLINE_BREAK_BUFFER_RATIO,
) -> float:
    bar_count = len(closes)
    if bar_count != len(highs) or bar_count != len(lows) or bar_count < 2 * swing_window_bars + 1:
        return 0.0

    swing_high_indices: list[int] = []
    for end_index in range(2 * swing_window_bars, bar_count):
        pivot = is_confirmed_swing_high(highs[: end_index + 1], swing_window_bars)
        if pivot is not None and (not swing_high_indices or pivot > swing_high_indices[-1]):
            swing_high_indices.append(pivot)

    if len(swing_high_indices) < 2:
        return 0.0

    first_index = swing_high_indices[-2]
    second_index = swing_high_indices[-1]
    if second_index - first_index < min_swing_separation_bars:
        return 0.0

    first_high = highs[first_index]
    second_high = highs[second_index]
    if first_high <= 0 or second_high <= 0:
        return 0.0
    midpoint = (first_high + second_high) / 2.0
    if abs(first_high - second_high) / midpoint > high_tolerance_ratio:
        return 0.0

    neckline = min(lows[first_index : second_index + 1])
    close = closes[-1]
    break_level = neckline * (1.0 - neckline_break_buffer_ratio)
    if close >= break_level:
        return 0.0

    separation_score = min(1.0, (second_index - first_index) / float(min_swing_separation_bars * 2))
    similarity_score = 1.0 - abs(first_high - second_high) / midpoint / high_tolerance_ratio
    similarity_score = max(0.0, min(1.0, similarity_score))
    break_score = min(1.0, (break_level - close) / break_level / 0.01) if break_level > 0 else 0.0
    return max(0.0, min(1.0, 0.4 * similarity_score + 0.3 * separation_score + 0.3 * break_score))
