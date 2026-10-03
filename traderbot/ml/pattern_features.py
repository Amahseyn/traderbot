from __future__ import annotations

from typing import Any

from traderbot.algorithms.patterns import double_bottom_score, double_top_score


def pattern_scores_through_index(
    bars: list[dict[str, Any]],
    end_index: int,
    *,
    swing_window_bars: int,
    min_swing_separation_bars: int,
    low_tolerance_ratio: float,
) -> tuple[float, float]:
    """Causal pattern scores using bars ``0..end_index`` inclusive."""
    if end_index < 0 or end_index >= len(bars):
        return 0.0, 0.0
    slice_bars = bars[: end_index + 1]
    lows = [float(bar["low"]) for bar in slice_bars]
    highs = [float(bar["high"]) for bar in slice_bars]
    closes = [float(bar["close"]) for bar in slice_bars]
    bottom = double_bottom_score(
        lows,
        highs,
        closes,
        swing_window_bars=swing_window_bars,
        min_swing_separation_bars=min_swing_separation_bars,
        low_tolerance_ratio=low_tolerance_ratio,
    )
    top = double_top_score(
        highs,
        lows,
        closes,
        swing_window_bars=swing_window_bars,
        min_swing_separation_bars=min_swing_separation_bars,
        high_tolerance_ratio=low_tolerance_ratio,
    )
    return bottom, top


def attach_pattern_feature_rows(
    bars: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    *,
    swing_window_bars = 3,
    min_swing_separation_bars = 4,
    low_tolerance_ratio = 0.02,
) -> None:
    """Merge ``pattern_double_bottom_score`` and ``pattern_double_top_score`` into feature rows."""
    if len(feature_rows) != len(bars):
        raise ValueError("feature_rows and bars length mismatch")
    for bar_index, row in enumerate(feature_rows):
        bottom, top = pattern_scores_through_index(
            bars,
            bar_index,
            swing_window_bars=swing_window_bars,
            min_swing_separation_bars=min_swing_separation_bars,
            low_tolerance_ratio=low_tolerance_ratio,
        )
        row["pattern_double_bottom_score"] = bottom
        row["pattern_double_top_score"] = top
