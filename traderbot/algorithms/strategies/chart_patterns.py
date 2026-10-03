from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.patterns import ChartPatternState


class ChartPatternsAlgorithm(Algorithm):
    """Double-bottom neckline break (buy) and double-top breakdown (sell)."""

    name = "chart_patterns"

    def __init__(
        self,
        *,
        swing_window_bars = 3,
        min_swing_separation_bars = 4,
        low_tolerance_ratio = 0.02,
        high_tolerance_ratio = 0.02,
        neckline_break_buffer_ratio = 0.0,
        pattern_score_threshold = 0.35,
    ):
        self._state = ChartPatternState(
            swing_window_bars=swing_window_bars,
            min_swing_separation_bars=min_swing_separation_bars,
            low_tolerance_ratio=low_tolerance_ratio,
            high_tolerance_ratio=high_tolerance_ratio,
            neckline_break_buffer_ratio=neckline_break_buffer_ratio,
            pattern_score_threshold=pattern_score_threshold,
        )

    def reset(self) -> None:
        self._state.reset()

    def on_bar(self, bar: Bar) -> SignalAction:
        bottom_score, top_score = self._state.update(bar)
        threshold = self._state.pattern_score_threshold
        if bottom_score >= threshold and bottom_score >= top_score:
            return "buy"
        if top_score >= threshold and top_score > bottom_score:
            return "sell"
        return "hold"
