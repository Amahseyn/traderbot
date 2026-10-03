from __future__ import annotations


def is_confirmed_swing_low(lows: list[float], swing_window_bars: int) -> int | None:
    """
    Causal swing low confirmed on the latest bar.

    The pivot is ``swing_window_bars`` bars before the latest close; it must be the
    minimum low over ``2 * swing_window_bars + 1`` bars ending at the latest bar.
    """
    if swing_window_bars < 1:
        raise ValueError("swing_window_bars must be >= 1")
    bar_count = len(lows)
    need = 2 * swing_window_bars + 1
    if bar_count < need:
        return None
    pivot_index = bar_count - 1 - swing_window_bars
    segment = lows[pivot_index - swing_window_bars : pivot_index + swing_window_bars + 1]
    pivot_low = lows[pivot_index]
    if pivot_low > min(segment):
        return None
    return pivot_index


def is_confirmed_swing_high(highs: list[float], swing_window_bars: int) -> int | None:
    if swing_window_bars < 1:
        raise ValueError("swing_window_bars must be >= 1")
    bar_count = len(highs)
    need = 2 * swing_window_bars + 1
    if bar_count < need:
        return None
    pivot_index = bar_count - 1 - swing_window_bars
    segment = highs[pivot_index - swing_window_bars : pivot_index + swing_window_bars + 1]
    pivot_high = highs[pivot_index]
    if pivot_high < max(segment):
        return None
    return pivot_index
