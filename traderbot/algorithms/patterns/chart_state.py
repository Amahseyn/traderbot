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

    def reset(self) -> None:
        self._lows.clear()
        self._highs.clear()
        self._closes.clear()

    def update(self, bar: dict[str, Any]) -> tuple[float, float]:
        self._lows.append(float(bar["low"]))
        self._highs.append(float(bar["high"]))
        self._closes.append(float(bar["close"]))
        bottom = double_bottom_score(
            self._lows,
            self._highs,
            self._closes,
            swing_window_bars=self.swing_window_bars,
            min_swing_separation_bars=self.min_swing_separation_bars,
            low_tolerance_ratio=self.low_tolerance_ratio,
            neckline_break_buffer_ratio=self.neckline_break_buffer_ratio,
        )
        top = double_top_score(
            self._highs,
            self._lows,
            self._closes,
            swing_window_bars=self.swing_window_bars,
            min_swing_separation_bars=self.min_swing_separation_bars,
            high_tolerance_ratio=self.high_tolerance_ratio,
            neckline_break_buffer_ratio=self.neckline_break_buffer_ratio,
        )
        return bottom, top
