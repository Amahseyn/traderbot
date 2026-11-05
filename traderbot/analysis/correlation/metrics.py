from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from traderbot.analysis.correlation.models import (
    CorrelationClassification,
    CorrelationRegimeAnalysis,
    RollingCorrelationPoint,
)


def _rank_array(values: np.ndarray) -> np.ndarray:
    """Compute fractional ranks (1-based, matching scipy.stats.rankdata)."""
    n = len(values)
    if n == 0:
        return np.empty(0, dtype=float)
    order = values.argsort()
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(1, n + 1, dtype=float)

    unique_vals, inverse_indices, counts = np.unique(values, return_inverse=True, return_counts=True)
    if len(unique_vals) < n:
        for val_idx, count in enumerate(counts):
            if count > 1:
                mask = inverse_indices == val_idx
                ranks[mask] = np.mean(ranks[mask])
    return ranks


def pearson_correlation(x: np.ndarray | Sequence[float], y: np.ndarray | Sequence[float]) -> float:
    """
    Sample Pearson correlation coefficient with divide-by-zero protection.
    Returns 0.0 for zero variance or insufficient data.
    """
    arr_x = np.asarray(x, dtype=float)
    arr_y = np.asarray(y, dtype=float)
    if len(arr_x) < 2 or len(arr_y) < 2 or len(arr_x) != len(arr_y):
        return 0.0

    mean_x = float(np.mean(arr_x))
    mean_y = float(np.mean(arr_y))
    dev_x = arr_x - mean_x
    dev_y = arr_y - mean_y

    var_x = float(np.sum(dev_x**2))
    var_y = float(np.sum(dev_y**2))

    if var_x <= 1e-15 or var_y <= 1e-15:
        return 0.0

    covariance = float(np.sum(dev_x * dev_y))
    corr = covariance / math.sqrt(var_x * var_y)
    return float(np.clip(corr, -1.0, 1.0))


def spearman_correlation(x: np.ndarray | Sequence[float], y: np.ndarray | Sequence[float]) -> float:
    """
    Spearman rank correlation coefficient: Pearson correlation applied to fractional ranks.
    """
    arr_x = np.asarray(x, dtype=float)
    arr_y = np.asarray(y, dtype=float)
    if len(arr_x) < 2 or len(arr_y) < 2 or len(arr_x) != len(arr_y):
        return 0.0

    ranks_x = _rank_array(arr_x)
    ranks_y = _rank_array(arr_y)
    return pearson_correlation(ranks_x, ranks_y)


def compute_rolling_correlation(
    returns_a: np.ndarray,
    returns_b: np.ndarray,
    timestamps: list[int],
    window_bars: int,
) -> list[RollingCorrelationPoint]:
    """
    Compute rolling window Pearson and Spearman correlations over aligned log-returns.
    """
    if len(returns_a) < window_bars or window_bars < 2:
        return []

    points: list[RollingCorrelationPoint] = []
    for end_idx in range(window_bars - 1, len(returns_a)):
        start_idx = end_idx - window_bars + 1
        sub_a = returns_a[start_idx : end_idx + 1]
        sub_b = returns_b[start_idx : end_idx + 1]
        ts = timestamps[end_idx]

        r = pearson_correlation(sub_a, sub_b)
        rho = spearman_correlation(sub_a, sub_b)
        points.append(RollingCorrelationPoint(timestamp=ts, pearson=r, spearman=rho))

    return points


def calculate_correlation_stability(rolling_points: list[RollingCorrelationPoint]) -> float:
    """
    Standard deviation of rolling Pearson correlation values.
    0.0 represents perfect stability across time.
    """
    if len(rolling_points) < 2:
        return 0.0
    pearsons = [p.pearson for p in rolling_points]
    return float(np.std(pearsons))


def classify_correlation(
    correlation: float,
    *,
    strong_pos: float = 0.70,
    mod_pos: float = 0.30,
    mod_neg: float = -0.30,
    strong_neg: float = -0.70,
) -> CorrelationClassification:
    """
    Categorize correlation into the 5 standard regime classifications:
    - strong_positive: >= 0.70
    - moderate_positive: 0.30 to 0.70
    - neutral: -0.30 to 0.30
    - moderate_negative: -0.70 to -0.30
    - strong_negative: <= -0.70
    """
    if correlation >= strong_pos:
        return CorrelationClassification.STRONG_POSITIVE
    if correlation >= mod_pos:
        return CorrelationClassification.MODERATE_POSITIVE
    if correlation > mod_neg:
        return CorrelationClassification.NEUTRAL
    if correlation > strong_neg:
        return CorrelationClassification.MODERATE_NEGATIVE
    return CorrelationClassification.STRONG_NEGATIVE


def analyze_regime_and_breakdown(
    rolling_points: list[RollingCorrelationPoint],
    *,
    tail_bars: int = 5,
    breakdown_delta: float = 0.40,
) -> CorrelationRegimeAnalysis:
    """
    Analyze rolling correlation path for persistence, breakdowns, and regime shifts.
    """
    if not rolling_points:
        return CorrelationRegimeAnalysis(
            is_persistent_negative=False,
            breakdown_detected=False,
            regime_shift_detected=False,
            recent_mean_correlation=0.0,
            historical_mean_correlation=0.0,
            correlation_divergence=0.0,
        )

    pearsons = [p.pearson for p in rolling_points]
    historical_mean = float(np.mean(pearsons))

    # Tail window (most recent observations)
    tail = pearsons[-tail_bars:] if len(pearsons) >= tail_bars else pearsons
    recent_mean = float(np.mean(tail))

    divergence = abs(recent_mean - historical_mean)
    breakdown = divergence >= breakdown_delta

    # Persistent negative: negative throughout at least 85% of windows and historical_mean < -0.30
    negative_count = sum(1 for val in pearsons if val <= -0.30)
    is_persistent_negative = (negative_count / len(pearsons) >= 0.85) and (historical_mean <= -0.30)

    # Early window
    early = pearsons[:tail_bars] if len(pearsons) >= tail_bars else pearsons
    early_mean = float(np.mean(early))

    # Regime shift: significant shift between early window and recent tail, or historical baseline and recent tail
    regime_shift = bool(
        (early_mean >= 0.30 and recent_mean <= -0.10)
        or (early_mean <= -0.30 and recent_mean >= 0.10)
        or (historical_mean >= 0.30 and recent_mean <= -0.10)
        or (historical_mean <= -0.30 and recent_mean >= 0.10)
        or (max(pearsons) - min(pearsons) >= 1.2 and (max(pearsons) * min(pearsons) < 0))
    )

    return CorrelationRegimeAnalysis(
        is_persistent_negative=is_persistent_negative,
        breakdown_detected=breakdown,
        regime_shift_detected=regime_shift,
        recent_mean_correlation=recent_mean,
        historical_mean_correlation=historical_mean,
        correlation_divergence=divergence,
    )
