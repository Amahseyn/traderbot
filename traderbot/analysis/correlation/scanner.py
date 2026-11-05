from __future__ import annotations

import time
from typing import Any

from traderbot.analysis.correlation.aligner import align_candles_for_correlation
from traderbot.analysis.correlation.metrics import (
    analyze_regime_and_breakdown,
    calculate_correlation_stability,
    classify_correlation,
    compute_rolling_correlation,
    pearson_correlation,
    spearman_correlation,
)
from traderbot.analysis.correlation.models import (
    CorrelationResult,
)
from traderbot.utils.resolution import resolution_minutes

SUPPORTED_TIMEFRAMES = ("1", "5", "15", "30", "60", "180", "240", "360", "720", "D")

DEFAULT_HORIZON_MINUTES: dict[str, int] = {
    "24h": 24 * 60,
    "1d": 24 * 60,
    "3d": 3 * 24 * 60,
    "7d": 7 * 24 * 60,
    "14d": 14 * 24 * 60,
    "30d": 30 * 24 * 60,
}


def horizon_to_observation_bars(horizon: str | int, timeframe: str) -> int:
    """
    Convert a time horizon (e.g. '24h', '3d', '7d', '14d', '30d') or integer count
    into observation bar counts using the resolution of the candle series.
    """
    if isinstance(horizon, int):
        return max(2, horizon)

    key = str(horizon).strip().lower()
    total_minutes = DEFAULT_HORIZON_MINUTES.get(key)
    if total_minutes is None:
        if key.endswith("h") and key[:-1].isdigit():
            total_minutes = int(key[:-1]) * 60
        elif key.endswith("d") and key[:-1].isdigit():
            total_minutes = int(key[:-1]) * 24 * 60
        elif key.isdigit():
            return max(2, int(key))
        else:
            raise ValueError(f"unsupported horizon: {horizon!r}; expected one of {list(DEFAULT_HORIZON_MINUTES.keys())}")

    bar_minutes = resolution_minutes(timeframe)
    bars = total_minutes // bar_minutes
    return max(2, bars)


class CorrelationScanner:
    """
    Institutional quantitative scanner for pairwise and multi-asset correlation analysis
    on synchronized log-return series across standardized horizons and resolutions.
    """

    def __init__(
        self,
        *,
        strong_pos: float = 0.70,
        mod_pos: float = 0.30,
        mod_neg: float = -0.30,
        strong_neg: float = -0.70,
        min_observations: int = 10,
    ) -> None:
        self.strong_pos = strong_pos
        self.mod_pos = mod_pos
        self.mod_neg = mod_neg
        self.strong_neg = strong_neg
        self.min_observations = min_observations

    def analyze_pair(
        self,
        bars_a: list[dict[str, Any]],
        bars_b: list[dict[str, Any]],
        *,
        symbol_a: str,
        symbol_b: str,
        timeframe: str = "60",
        window_horizon: str | int = "24h",
        breakdown_delta: float = 0.40,
    ) -> CorrelationResult:
        """
        Perform complete correlation analysis on two candle series.
        Calculates Pearson, Spearman, rolling correlation, stability, classification,
        and regime/breakdown metrics.
        """
        aligned = align_candles_for_correlation(
            bars_a,
            bars_b,
            resolution=timeframe,
            min_observations=self.min_observations,
        )

        n_obs = len(aligned.returns_a)
        now_ts = int(time.time())

        if n_obs < 2:
            classification = classify_correlation(
                0.0,
                strong_pos=self.strong_pos,
                mod_pos=self.mod_pos,
                mod_neg=self.mod_neg,
                strong_neg=self.strong_neg,
            )
            regime = analyze_regime_and_breakdown([], breakdown_delta=breakdown_delta)
            return CorrelationResult(
                symbol_a=symbol_a,
                symbol_b=symbol_b,
                timeframe=timeframe,
                pearson=0.0,
                spearman=0.0,
                rolling_correlation=[],
                correlation_stability=0.0,
                classification=classification,
                observation_count=n_obs,
                calculation_timestamp=now_ts,
                regime_analysis=regime,
                data_quality=aligned.quality_report,
            )

        pearson = pearson_correlation(aligned.returns_a, aligned.returns_b)
        spearman = spearman_correlation(aligned.returns_a, aligned.returns_b)

        window_bars = horizon_to_observation_bars(window_horizon, timeframe)
        # If dataset is shorter than desired window horizon, use a scaled fraction or full length
        effective_window = min(window_bars, n_obs)
        rolling = compute_rolling_correlation(
            aligned.returns_a,
            aligned.returns_b,
            aligned.timestamps,
            effective_window,
        )

        stability = calculate_correlation_stability(rolling)
        classification = classify_correlation(
            pearson,
            strong_pos=self.strong_pos,
            mod_pos=self.mod_pos,
            mod_neg=self.mod_neg,
            strong_neg=self.strong_neg,
        )
        regime = analyze_regime_and_breakdown(rolling, breakdown_delta=breakdown_delta)

        return CorrelationResult(
            symbol_a=symbol_a,
            symbol_b=symbol_b,
            timeframe=timeframe,
            pearson=pearson,
            spearman=spearman,
            rolling_correlation=rolling,
            correlation_stability=stability,
            classification=classification,
            observation_count=n_obs,
            calculation_timestamp=now_ts,
            regime_analysis=regime,
            data_quality=aligned.quality_report,
        )

    def scan_universe(
        self,
        bars_by_symbol: dict[str, list[dict[str, Any]]],
        *,
        timeframe: str = "60",
        window_horizon: str | int = "24h",
    ) -> list[CorrelationResult]:
        """
        Scan all pairwise combinations in a multi-asset universe.
        """
        symbols = sorted(bars_by_symbol.keys())
        results: list[CorrelationResult] = []

        for idx_a in range(len(symbols)):
            for idx_b in range(idx_a + 1, len(symbols)):
                sym_a = symbols[idx_a]
                sym_b = symbols[idx_b]
                res = self.analyze_pair(
                    bars_by_symbol[sym_a],
                    bars_by_symbol[sym_b],
                    symbol_a=sym_a,
                    symbol_b=sym_b,
                    timeframe=timeframe,
                    window_horizon=window_horizon,
                )
                results.append(res)

        return results

