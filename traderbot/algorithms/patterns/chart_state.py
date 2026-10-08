from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from traderbot.algorithms.patterns.constants import (
    DEFAULT_LOW_TOLERANCE_RATIO,
    DEFAULT_MIN_SWING_SEPARATION_BARS,
    DEFAULT_NECKLINE_BREAK_BUFFER_RATIO,
    DEFAULT_SWING_WINDOW_BARS,
)
from traderbot.algorithms.patterns.double_bottom import double_bottom_score
from traderbot.algorithms.patterns.double_top import double_top_score
from traderbot.algorithms.patterns.swings import is_confirmed_swing_high, is_confirmed_swing_low


@dataclass
class ChartPatternState:
    swing_window_bars: int = DEFAULT_SWING_WINDOW_BARS
    min_swing_separation_bars: int = DEFAULT_MIN_SWING_SEPARATION_BARS
    low_tolerance_ratio: float = DEFAULT_LOW_TOLERANCE_RATIO
    high_tolerance_ratio: float = DEFAULT_LOW_TOLERANCE_RATIO
    neckline_break_buffer_ratio: float = DEFAULT_NECKLINE_BREAK_BUFFER_RATIO
    pattern_score_threshold: float = 0.35
    _lows: list[float] = field(default_factory=list)
    _highs: list[float] = field(default_factory=list)
    _closes: list[float] = field(default_factory=list)
    _swing_low_indices: list[int] = field(default_factory=list)
    _swing_high_indices: list[int] = field(default_factory=list)
    _last_bottom_score: float = 0.0
    _last_top_score: float = 0.0

    def reset(self) -> None:
        self._lows.clear()
        self._highs.clear()
        self._closes.clear()
        self._swing_low_indices.clear()
        self._swing_high_indices.clear()
        self._last_bottom_score = 0.0
        self._last_top_score = 0.0

    def _track_swings(self) -> None:
        pivot_low = is_confirmed_swing_low(self._lows, self.swing_window_bars)
        if pivot_low is not None and (
            not self._swing_low_indices or pivot_low > self._swing_low_indices[-1]
        ):
            self._swing_low_indices.append(pivot_low)
        pivot_high = is_confirmed_swing_high(self._highs, self.swing_window_bars)
        if pivot_high is not None and (
            not self._swing_high_indices or pivot_high > self._swing_high_indices[-1]
        ):
            self._swing_high_indices.append(pivot_high)

    def update(self, bar: dict[str, Any]) -> tuple[float, float]:
        self._lows.append(float(bar["low"]))
        self._highs.append(float(bar["high"]))
        self._closes.append(float(bar["close"]))
        self._track_swings()
        bottom = double_bottom_score(
            self._lows,
            self._highs,
            self._closes,
            swing_window_bars=self.swing_window_bars,
            min_swing_separation_bars=self.min_swing_separation_bars,
            low_tolerance_ratio=self.low_tolerance_ratio,
            neckline_break_buffer_ratio=self.neckline_break_buffer_ratio,
            swing_low_indices=self._swing_low_indices,
        )
        top = double_top_score(
            self._highs,
            self._lows,
            self._closes,
            swing_window_bars=self.swing_window_bars,
            min_swing_separation_bars=self.min_swing_separation_bars,
            high_tolerance_ratio=self.high_tolerance_ratio,
            neckline_break_buffer_ratio=self.neckline_break_buffer_ratio,
            swing_high_indices=self._swing_high_indices,
        )
        threshold = self.pattern_score_threshold
        edge_bottom = bottom if bottom >= threshold and self._last_bottom_score < threshold else 0.0
        edge_top = top if top >= threshold and self._last_top_score < threshold else 0.0
        self._last_bottom_score = bottom
        self._last_top_score = top
        return edge_bottom, edge_top
