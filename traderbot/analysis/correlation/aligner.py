from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from traderbot.analysis.correlation.models import DataQualityReport
from traderbot.utils.bars import normalize_bar
from traderbot.utils.resolution import resolution_minutes


@dataclass(frozen=True, slots=True)
class AlignedReturnSeries:
    timestamps: list[int]
    returns_a: np.ndarray
    returns_b: np.ndarray
    closes_a: np.ndarray
    closes_b: np.ndarray
    quality_report: DataQualityReport


def _deduplicate_and_sort_bars(bars: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Sort chronologically and deduplicate bars by open timestamp (keeping last occurrence)."""
    by_timestamp: dict[int, dict[str, Any]] = {}
    duplicate_count = 0
    for raw in bars:
        bar = normalize_bar(raw)
        timestamp = int(bar["timestamp"])
        if timestamp in by_timestamp:
            duplicate_count += 1
        by_timestamp[timestamp] = bar

    sorted_bars = [by_timestamp[ts] for ts in sorted(by_timestamp.keys())]
    return sorted_bars, duplicate_count


def _count_missing_intervals(sorted_bars: list[dict[str, Any]], expected_step_seconds: int) -> int:
    """Detect time gaps exceeding the expected bar resolution."""
    if len(sorted_bars) < 2 or expected_step_seconds <= 0:
        return 0
    missing = 0
    for idx in range(1, len(sorted_bars)):
        diff = int(sorted_bars[idx]["timestamp"]) - int(sorted_bars[idx - 1]["timestamp"])
        if diff > expected_step_seconds:
            gap_count = (diff // expected_step_seconds) - 1
            missing += max(0, gap_count)
    return missing


def align_candles_for_correlation(
    bars_a: list[dict[str, Any]],
    bars_b: list[dict[str, Any]],
    resolution: str,
    *,
    min_observations: int = 10,
) -> AlignedReturnSeries:
    """
    Synchronize two OHLC candle series on matching timestamps, enforce data quality standards,
    and compute matched log-returns: r_t = ln(close_t / close_{t-1}).
    """
    bar_minutes = resolution_minutes(resolution)
    step_seconds = bar_minutes * 60

    sorted_a, dups_a = _deduplicate_and_sort_bars(bars_a)
    sorted_b, dups_b = _deduplicate_and_sort_bars(bars_b)

    missing_a = _count_missing_intervals(sorted_a, step_seconds)
    missing_b = _count_missing_intervals(sorted_b, step_seconds)

    map_b = {int(b["timestamp"]): float(b["close"]) for b in sorted_b}

    matched_timestamps: list[int] = []
    matched_closes_a: list[float] = []
    matched_closes_b: list[float] = []

    for bar_a in sorted_a:
        ts = int(bar_a["timestamp"])
        if ts in map_b:
            close_a = float(bar_a["close"])
            close_b = map_b[ts]
            if close_a > 0 and close_b > 0 and math.isfinite(close_a) and math.isfinite(close_b):
                matched_timestamps.append(ts)
                matched_closes_a.append(close_a)
                matched_closes_b.append(close_b)

    notes: list[str] = []
    if dups_a + dups_b > 0:
        notes.append(f"Deduplicated {dups_a + dups_b} duplicate candles")
    if missing_a > 0 or missing_b > 0:
        notes.append(f"Gaps detected: {missing_a} missing intervals in A, {missing_b} in B")

    if len(matched_timestamps) < min_observations:
        notes.append(f"Insufficient aligned observations ({len(matched_timestamps)} < {min_observations})")

    # Compute log returns: r_t = ln(P_t / P_{t-1})
    if len(matched_timestamps) >= 2:
        closes_a_arr = np.asarray(matched_closes_a, dtype=float)
        closes_b_arr = np.asarray(matched_closes_b, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            returns_a = np.log(closes_a_arr[1:] / closes_a_arr[:-1])
            returns_b = np.log(closes_b_arr[1:] / closes_b_arr[:-1])
        return_timestamps = matched_timestamps[1:]
    else:
        returns_a = np.empty(0, dtype=float)
        returns_b = np.empty(0, dtype=float)
        return_timestamps = []

    # Check for zero variance / stale data
    zero_var_a = bool(len(returns_a) > 0 and float(np.var(returns_a)) == 0.0)
    zero_var_b = bool(len(returns_b) > 0 and float(np.var(returns_b)) == 0.0)
    zero_variance = zero_var_a or zero_var_b
    if zero_variance:
        notes.append("Stale data detected: return series has zero variance")

    quality_report = DataQualityReport(
        total_bars_a=len(bars_a),
        total_bars_b=len(bars_b),
        aligned_bars=len(return_timestamps),
        missing_bars_a=missing_a,
        missing_bars_b=missing_b,
        duplicate_timestamps_dropped=dups_a + dups_b,
        zero_variance_detected=zero_variance,
        quality_notes=notes,
    )

    return AlignedReturnSeries(
        timestamps=return_timestamps,
        returns_a=returns_a,
        returns_b=returns_b,
        closes_a=np.asarray(matched_closes_a, dtype=float),
        closes_b=np.asarray(matched_closes_b, dtype=float),
        quality_report=quality_report,
    )

