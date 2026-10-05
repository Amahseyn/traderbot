from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from traderbot.utils.resolution import resolution_from_csv_path, resolution_minutes
from traderbot.utils.bars import load_bars_csv, one_minute_bars_known_at
from traderbot.utils.constants import (
    INTRAHOUR_FEATURE_KEYS,
    INTRAHOUR_RETURN_15_MINUTE_BARS,
    INTRAHOUR_RETURN_5_MINUTE_BARS,
    INTRAHOUR_RETURN_60_MINUTE_BARS,
    ONE_MINUTE_BAR_MINUTES,
    SECONDS_PER_MINUTE,
)


def one_minute_csv_for_coarse(coarse_csv_path: Path, one_minute_csv: Path | None = None) -> Path | None:
    """Sibling ``{base}_1.csv`` for any ``{base}_{resolution}.csv`` in the same directory."""
    if one_minute_csv is not None:
        return one_minute_csv if one_minute_csv.is_file() else None
    stem = coarse_csv_path.stem
    if "_" not in stem:
        return None
    base, _resolution_suffix = stem.rsplit("_", 1)
    candidate = coarse_csv_path.with_name(f"{base}_1.csv")
    return candidate if candidate.is_file() else None


def load_one_minute_bars(
    coarse_csv: Path,
    one_minute_csv: Path | None = None,
    *,
    auto_load = True,
    known_at_unix_seconds: int | None = None,
    bar_minutes: int = ONE_MINUTE_BAR_MINUTES,
) -> list[dict[str, Any]] | None:
    """
    Load 1m OHLC CSV for a coarse ``{base}_{resolution}.csv`` (sibling or explicit path).

    With ``known_at_unix_seconds``, only bars already closed at that instant are returned.
    """
    if not auto_load and one_minute_csv is None:
        return None
    path = one_minute_csv_for_coarse(coarse_csv, one_minute_csv)
    if path is None:
        return None
    bars = load_bars_csv(path)
    if not bars:
        return None
    if known_at_unix_seconds is not None:
        bars = one_minute_bars_known_at(bars, known_at_unix_seconds, bar_minutes=bar_minutes)
    return bars if bars else None


def coarse_minutes_for_csv(csv_path: Path) -> int:
    return resolution_minutes(resolution_from_csv_path(csv_path.name))


def _one_minute_bars_in_coarse_window(
    one_minute_bars: list[dict[str, Any]],
    *,
    coarse_bar_open_unix_seconds: int,
    coarse_window_seconds: int,
) -> list[dict[str, Any]]:
    coarse_window_end_unix_seconds = coarse_bar_open_unix_seconds + coarse_window_seconds
    return [
        bar
        for bar in one_minute_bars
        if coarse_bar_open_unix_seconds <= int(bar["timestamp"]) < coarse_window_end_unix_seconds
    ]


def intrahour_features_from_group(
    group: list[dict[str, Any]],
    *,
    coarse_open: float,
) -> dict[str, float | None]:
    empty = {k: None for k in INTRAHOUR_FEATURE_KEYS}
    if not group or coarse_open <= 0:
        return empty
    closes = [float(b["close"]) for b in group]
    last = closes[-1]
    out: dict[str, float | None] = {
        "fine_return_in_bar": last / coarse_open - 1.0,
    }

    def tail_return(bar_count: int) -> float | None:
        if len(closes) < bar_count:
            return None
        start_close = closes[-bar_count]
        if start_close <= 0:
            return None
        return last / start_close - 1.0

    out["fine_return_last_5m"] = tail_return(INTRAHOUR_RETURN_5_MINUTE_BARS)
    out["fine_return_last_15m"] = tail_return(INTRAHOUR_RETURN_15_MINUTE_BARS)
    out["fine_return_last_60m"] = tail_return(INTRAHOUR_RETURN_60_MINUTE_BARS)
    return out


def intrahour_features_for_coarse_bars(
    coarse_bars: list[dict[str, Any]],
    one_minute_bars: list[dict[str, Any]],
    *,
    coarse_minutes: int,
    one_minute_bar_minutes: int = ONE_MINUTE_BAR_MINUTES,
) -> list[dict[str, float | None]]:
    if coarse_minutes < 1 or one_minute_bar_minutes < 1:
        raise ValueError("coarse_minutes and one_minute_bar_minutes must be >= 1")
    if coarse_minutes % one_minute_bar_minutes != 0:
        raise ValueError("coarse_minutes must be a multiple of one_minute_bar_minutes")
    coarse_window_seconds = coarse_minutes * SECONDS_PER_MINUTE
    one_minute_bars_sorted = sorted(one_minute_bars, key=lambda bar: int(bar["timestamp"]))
    return [
        intrahour_features_from_group(
            _one_minute_bars_in_coarse_window(
                one_minute_bars_sorted,
                coarse_bar_open_unix_seconds=int(coarse_bar["timestamp"]),
                coarse_window_seconds=coarse_window_seconds,
            ),
            coarse_open=float(coarse_bar["open"]),
        )
        for coarse_bar in coarse_bars
    ]


def attach_intrahour_to_bars(
    coarse_bars: list[dict[str, Any]],
    one_minute_bars: list[dict[str, Any]] | None,
    *,
    coarse_minutes: int,
    one_minute_bar_minutes: int = ONE_MINUTE_BAR_MINUTES,
) -> list[dict[str, Any]]:
    if not coarse_bars or not one_minute_bars:
        return coarse_bars
    feature_rows = intrahour_features_for_coarse_bars(
        coarse_bars,
        one_minute_bars,
        coarse_minutes=coarse_minutes,
        one_minute_bar_minutes=one_minute_bar_minutes,
    )
    merged: list[dict[str, Any]] = []
    for coarse_bar, features in zip(coarse_bars, feature_rows, strict=True):
        row = dict(coarse_bar)
        for key, value in features.items():
            if value is not None:
                row[key] = value
        merged.append(row)
    return merged


def maybe_enrich_coarse_from_fine_csv(
    coarse_bars: list[dict[str, Any]],
    coarse_path: Path,
    *,
    coarse_minutes: int | None = None,
    one_minute_csv: Path | None = None,
    one_minute_bar_minutes: int = ONE_MINUTE_BAR_MINUTES,
    auto_fine = True,
) -> list[dict[str, Any]]:
    if not auto_fine and one_minute_csv is None:
        return coarse_bars
    one_minute_bars = load_one_minute_bars(coarse_path, one_minute_csv, auto_load=auto_fine)
    if not one_minute_bars:
        return coarse_bars
    coarse_bar_minutes = coarse_minutes if coarse_minutes is not None else coarse_minutes_for_csv(coarse_path)
    return attach_intrahour_to_bars(
        coarse_bars,
        one_minute_bars,
        coarse_minutes=coarse_bar_minutes,
        one_minute_bar_minutes=one_minute_bar_minutes,
    )


def enrich_bars_for_csv(
    bars: list[dict[str, Any]],
    csv_path: Path,
    args: argparse.Namespace | None = None,
    *,
    one_minute_csv: Path | None = None,
    auto_fine = True,
) -> list[dict[str, Any]]:
    if args is not None:
        auto_fine = not getattr(args, "no_auto_fine", False)
        one_minute_csv = getattr(args, "fine_csv", None) or one_minute_csv
    return maybe_enrich_coarse_from_fine_csv(
        bars,
        csv_path,
        one_minute_csv=one_minute_csv,
        auto_fine=auto_fine,
    )


def add_fine_coarse_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fine-csv",
        type=Path,
        default=None,
        help="1m OHLC CSV for intrahour features (default: sibling {base}_1.csv)",
    )
    parser.add_argument(
        "--no-auto-fine",
        action="store_true",
        help="Do not load sibling 1m CSV for intrahour enrichment",
    )
