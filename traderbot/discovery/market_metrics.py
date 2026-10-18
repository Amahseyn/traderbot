from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from traderbot.utils.indicators import atr


@dataclass(frozen=True, slots=True)
class MarketBarMetrics:
    mean_quote_volume: float
    return_1bar_pct: float | None
    return_7bar_pct: float | None
    return_30bar_pct: float | None
    realized_vol_pct: float | None
    range_pct_1bar: float | None
    atr_pct: float | None


def _safe_pct(numerator: float, denominator: float) -> float | None:
    if denominator <= 0 or not math.isfinite(denominator) or not math.isfinite(numerator):
        return None
    return (numerator / denominator - 1.0) * 100.0


def _mean_quote_volume(bars: list[dict[str, Any]], tail: int = 24) -> float:
    if not bars:
        return 0.0
    window = bars[-tail:] if len(bars) >= tail else bars
    total = 0.0
    for bar in window:
        volume = float(bar.get("volume") or 0)
        close = float(bar.get("close") or 0)
        total += volume * close
    return total / len(window)


def _return_over_bars(bars: list[dict[str, Any]], lookback_bars: int) -> float | None:
    if len(bars) <= lookback_bars:
        return None
    close_now = float(bars[-1]["close"])
    close_then = float(bars[-1 - lookback_bars]["close"])
    return _safe_pct(close_now, close_then)


def _realized_vol_pct(bars: list[dict[str, Any]], window: int = 20) -> float | None:
    if len(bars) < window + 1:
        return None
    closes = [float(bar["close"]) for bar in bars[-(window + 1) :]]
    returns: list[float] = []
    for index in range(1, len(closes)):
        if closes[index - 1] <= 0:
            continue
        returns.append((closes[index] / closes[index - 1]) - 1.0)
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    stdev = math.sqrt(variance)
    return stdev * 100.0


def compute_market_bar_metrics(bars: list[dict[str, Any]]) -> MarketBarMetrics:
    if not bars:
        return MarketBarMetrics(
            mean_quote_volume=0.0,
            return_1bar_pct=None,
            return_7bar_pct=None,
            return_30bar_pct=None,
            realized_vol_pct=None,
            range_pct_1bar=None,
            atr_pct=None,
        )
    last = bars[-1]
    close = float(last.get("close") or 0)
    high = float(last.get("high") or close)
    low = float(last.get("low") or close)
    range_pct = ((high - low) / close * 100.0) if close > 0 else None

    highs = [float(bar["high"]) for bar in bars]
    lows = [float(bar["low"]) for bar in bars]
    closes = [float(bar["close"]) for bar in bars]
    atr_series = atr(highs, lows, closes, 14)
    atr_value = atr_series[-1] if atr_series else None
    atr_pct = (atr_value / close * 100.0) if atr_value is not None and close > 0 else None

    return MarketBarMetrics(
        mean_quote_volume=_mean_quote_volume(bars),
        return_1bar_pct=_return_over_bars(bars, 1),
        return_7bar_pct=_return_over_bars(bars, 7),
        return_30bar_pct=_return_over_bars(bars, 30),
        realized_vol_pct=_realized_vol_pct(bars),
        range_pct_1bar=range_pct,
        atr_pct=atr_pct,
    )


def market_metrics_to_dict(metrics: MarketBarMetrics) -> dict[str, float | None]:
    return {
        "mean_quote_volume": metrics.mean_quote_volume,
        "return_1bar_pct": metrics.return_1bar_pct,
        "return_7bar_pct": metrics.return_7bar_pct,
        "return_30bar_pct": metrics.return_30bar_pct,
        "realized_vol_pct": metrics.realized_vol_pct,
        "range_pct_1bar": metrics.range_pct_1bar,
        "atr_pct": metrics.atr_pct,
    }


def _normalize_positive(value: float | None, cap: float) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    if value <= 0:
        return 0.0
    return min(1.0, value / cap)


def _normalize_signed_return(return_pct: float | None, cap: float) -> float | None:
    if return_pct is None or not math.isfinite(return_pct):
        return None
    if return_pct <= 0:
        return 0.0
    return min(1.0, return_pct / cap)


def score_market_opportunity(
    metrics: MarketBarMetrics,
    *,
    volume_percentile: float | None,
    return_cap_pct: float = 15.0,
    vol_cap_pct: float = 5.0,
) -> tuple[float | None, dict[str, float]]:
    """Composite 0–1 score for market-only discovery (no strategies)."""
    components: dict[str, float | None] = {
        "volume": volume_percentile,
        "return_1bar": _normalize_signed_return(metrics.return_1bar_pct, return_cap_pct),
        "return_7bar": _normalize_signed_return(metrics.return_7bar_pct, return_cap_pct * 2),
        "return_30bar": _normalize_signed_return(metrics.return_30bar_pct, return_cap_pct * 4),
        "volatility": _normalize_positive(metrics.realized_vol_pct, vol_cap_pct),
        "range": _normalize_positive(metrics.range_pct_1bar, vol_cap_pct),
    }
    weights = {
        "volume": 0.30,
        "return_1bar": 0.15,
        "return_7bar": 0.20,
        "return_30bar": 0.15,
        "volatility": 0.10,
        "range": 0.10,
    }
    weighted_sum = 0.0
    active_weight = 0.0
    scored: dict[str, float] = {}
    for name, weight in weights.items():
        value = components.get(name)
        if value is None:
            continue
        weighted_sum += weight * value
        active_weight += weight
        scored[name] = round(value, 6)
    if active_weight <= 0:
        return None, scored
    return round(weighted_sum / active_weight, 6), scored


def volume_percentiles(values: list[float]) -> list[float]:
    """Map each value to its percentile rank in [0, 1] across the batch."""
    if not values:
        return []
    indexed = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    for rank, (original_index, _) in enumerate(indexed):
        ranks[original_index] = rank / max(1, len(values) - 1)
    return ranks
