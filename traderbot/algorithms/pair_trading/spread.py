"""
Spread and z-score for two-asset stat-arb / pair trading.

Adapted from Hummingbot ``controllers/generic/stat_arb.py`` (Apache-2.0); see
``traderbot/third_party/NOTICES.md``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class SpreadSnapshot:
    spread_pct: float
    z_score: float
    hedge_beta: float
    hedge_alpha: float


def _linear_regression(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Return (intercept, slope) for y ~ alpha + beta * x."""
    if len(x) < 2:
        return float(y[-1]), 0.0
    x_mean = float(np.mean(x))
    y_mean = float(np.mean(y))
    variance = float(np.var(x))
    if variance == 0.0:
        return y_mean, 0.0
    covariance = float(np.mean((x - x_mean) * (y - y_mean)))
    beta = covariance / variance
    alpha = y_mean - beta * x_mean
    return alpha, beta


def spread_z_score_from_closes(
    dominant_closes: np.ndarray,
    hedge_closes: np.ndarray,
    *,
    lookback_period: int,
) -> SpreadSnapshot | None:
    """
    Compute the latest spread (percent) and z-score using cumulative-return regression,
    matching Hummingbot's ``StatArb.get_spread_and_z_score`` logic.
    """
    if lookback_period < 2:
        raise ValueError("lookback_period must be >= 2")
    min_length = min(len(dominant_closes), len(hedge_closes))
    if min_length < lookback_period:
        return None

    dominant_prices = np.asarray(dominant_closes[-lookback_period:], dtype=float)
    hedge_prices = np.asarray(hedge_closes[-lookback_period:], dtype=float)

    dominant_pct_change = np.diff(dominant_prices) / dominant_prices[:-1]
    hedge_pct_change = np.diff(hedge_prices) / hedge_prices[:-1]

    dominant_cum = np.cumprod(dominant_pct_change + 1.0)
    hedge_cum = np.cumprod(hedge_pct_change + 1.0)
    if len(dominant_cum) == 0:
        return None

    dominant_cum = dominant_cum / dominant_cum[0]
    hedge_cum = hedge_cum / hedge_cum[0]

    alpha, beta = _linear_regression(dominant_cum, hedge_cum)
    y_pred = alpha + beta * dominant_cum
    with np.errstate(divide="ignore", invalid="ignore"):
        spread_pct = (hedge_cum - y_pred) / y_pred * 100.0

    mean_spread = float(np.mean(spread_pct))
    std_spread = float(np.std(spread_pct))
    if std_spread == 0.0:
        return None

    current_spread = float(spread_pct[-1])
    z_score = (current_spread - mean_spread) / std_spread
    return SpreadSnapshot(
        spread_pct=current_spread,
        z_score=z_score,
        hedge_beta=beta,
        hedge_alpha=alpha,
    )


def align_bars_by_timestamp(
    dominant_bars: list[dict],
    hedge_bars: list[dict],
) -> list[dict]:
    """Merge two OHLC series on matching bar open timestamps; dominant bar is the base."""
    hedge_by_timestamp = {int(bar["timestamp"]): bar for bar in hedge_bars}
    aligned: list[dict] = []
    for dominant_bar in dominant_bars:
        timestamp = int(dominant_bar["timestamp"])
        hedge_bar = hedge_by_timestamp.get(timestamp)
        if hedge_bar is None:
            continue
        merged = dict(dominant_bar)
        merged["hedge_close"] = float(hedge_bar["close"])
        merged["hedge_open"] = float(hedge_bar.get("open", hedge_bar["close"]))
        merged["hedge_high"] = float(hedge_bar.get("high", hedge_bar["close"]))
        merged["hedge_low"] = float(hedge_bar.get("low", hedge_bar["close"]))
        aligned.append(merged)
    return aligned
