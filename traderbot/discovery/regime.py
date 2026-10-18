from __future__ import annotations

from typing import Any, Protocol

from traderbot.utils.indicators import atr


class RegimeClassifier(Protocol):
    def label_at_bar(self, bars: list[dict[str, Any]], bar_index: int) -> str:
        """Classify regime using only bars[0 : bar_index + 1] (inclusive close)."""


class MaSlopeVolatilityRegime:
    """Causal regime labels from MA slope and ATR relative to price."""

    def __init__(
        self,
        *,
        ma_period: int = 20,
        atr_period: int = 14,
        trend_slope_threshold: float = 0.0015,
        high_vol_atr_pct: float = 0.025,
        low_vol_atr_pct: float = 0.008,
    ) -> None:
        self.ma_period = ma_period
        self.atr_period = atr_period
        self.trend_slope_threshold = trend_slope_threshold
        self.high_vol_atr_pct = high_vol_atr_pct
        self.low_vol_atr_pct = low_vol_atr_pct

    def label_at_bar(self, bars: list[dict[str, Any]], bar_index: int) -> str:
        window = bars[: bar_index + 1]
        if len(window) < max(self.ma_period + 1, self.atr_period + 1):
            return "uncertain"
        closes = [float(bar["close"]) for bar in window]
        highs = [float(bar["high"]) for bar in window]
        lows = [float(bar["low"]) for bar in window]
        ma_now = sum(closes[-self.ma_period :]) / self.ma_period
        ma_prev = sum(closes[-self.ma_period - 1 : -1]) / self.ma_period
        if ma_prev <= 0:
            return "uncertain"
        slope = (ma_now - ma_prev) / ma_prev
        atr_series = atr(highs, lows, closes, self.atr_period)
        atr_value = atr_series[-1]
        if atr_value is None or closes[-1] <= 0:
            return "uncertain"
        atr_pct = atr_value / closes[-1]
        trending = abs(slope) >= self.trend_slope_threshold
        if atr_pct >= self.high_vol_atr_pct:
            return "high_volatility" if not trending else "trending_high_vol"
        if atr_pct <= self.low_vol_atr_pct:
            return "low_volatility" if not trending else "trending_low_vol"
        if trending:
            return "trending" if slope > 0 else "trending_down"
        return "range_bound"


def regime_label_for_bars(bars: list[dict[str, Any]], classifier: RegimeClassifier | None = None) -> str:
    """Regime at the last bar close (evaluation snapshot)."""
    if not bars:
        return "uncertain"
    model = classifier or MaSlopeVolatilityRegime()
    return model.label_at_bar(bars, len(bars) - 1)
