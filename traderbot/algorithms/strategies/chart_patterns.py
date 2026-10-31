from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.patterns import ChartPatternState
from traderbot.algorithms.price_context import signal_clears_cost
from traderbot.algorithms.validators import validate_cost_edge


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
        min_edge_over_cost: float | None = None,
        roundtrip_cost_pct: float | None = None,
    ):
        validate_cost_edge(min_edge_over_cost, roundtrip_cost_pct)
        self.min_edge_over_cost = 0.0 if min_edge_over_cost is None else float(min_edge_over_cost)
        self.roundtrip_cost_pct = roundtrip_cost_pct
        self._state = ChartPatternState(
            swing_window_bars=swing_window_bars,
            min_swing_separation_bars=min_swing_separation_bars,
            low_tolerance_ratio=low_tolerance_ratio,
            high_tolerance_ratio=high_tolerance_ratio,
            neckline_break_buffer_ratio=neckline_break_buffer_ratio,
            pattern_score_threshold=pattern_score_threshold,
        )
        self._in_long = False
        self._stop_price: float | None = None

    def reset(self) -> None:
        self._state.reset()
        self._in_long = False
        self._stop_price = None

    def sync_open_position(self, in_position: bool) -> None:
        if not in_position:
            self._in_long = False
            self._stop_price = None

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        low = float(bar["low"])
        if self._in_long:
            if self._stop_price is not None and low <= self._stop_price:
                self._in_long = False
                self._stop_price = None
                return "sell"
        bottom_score, top_score = self._state.update(bar)
        threshold = self._state.pattern_score_threshold
        if bottom_score >= threshold and bottom_score >= top_score:
            expected_move_pct = 0.0
            stop_px = None
            if len(self._state._swing_low_indices) >= 2:
                idx1 = self._state._swing_low_indices[-2]
                idx2 = self._state._swing_low_indices[-1]
                trough = min(self._state._lows[idx1], self._state._lows[idx2])
                neckline = max(self._state._highs[idx1 : idx2 + 1])
                height = neckline - trough
                if close > 0 and height > 0:
                    expected_move_pct = height / close
                    stop_px = neckline - 0.5 * height
            if not signal_clears_cost(
                expected_move_pct,
                min_edge_over_cost=self.min_edge_over_cost,
                roundtrip_cost_pct=self.roundtrip_cost_pct,
            ):
                return "hold"
            self._in_long = True
            self._stop_price = stop_px
            return "buy"
        if top_score >= threshold and top_score > bottom_score:
            self._in_long = False
            self._stop_price = None
            return "sell"
        return "hold"
