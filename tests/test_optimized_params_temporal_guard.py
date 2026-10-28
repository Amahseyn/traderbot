"""Temporal-leakage guard for ``apply_sweep_winner`` (audit item 4).

A sweep record whose ``optimize_end_utc`` is at or after the compare run's
``run_start_unix_seconds`` was trained on data overlapping the evaluation
window and must not be applied.  This test verifies the guard rejects such
records and falls back to an earlier, temporally-eligible record.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from traderbot.algorithms.optimized_params import (
    _iso_utc_to_unix,
    _record_is_temporally_eligible,
    resolve_best_sweep_params,
)


def _make_db(records: list[tuple[str, str, str, str]]) -> Path:
    """records: list of (id, best_params_json, optimize_end_utc, created_at_utc)."""
    tmp = tempfile.mkdtemp()
    db = Path(tmp) / "sweep.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE sweep_sessions (
            id TEXT PRIMARY KEY,
            strategy_id TEXT,
            symbol TEXT,
            resolution TEXT,
            horizon_label TEXT,
            best_params_json TEXT,
            optimize_start_utc TEXT,
            optimize_end_utc TEXT,
            compare_start_utc TEXT,
            compare_end_utc TEXT,
            created_at_utc TEXT
        );
        """
    )
    for rid, params, end_utc, created_utc in records:
        conn.execute(
            "INSERT INTO sweep_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, "sma_cross", "BTCUSDT", "60", None, params, None, end_utc, None, None, created_utc),
        )
    conn.commit()
    conn.close()
    return db


def test_iso_utc_to_unix_parses_z_suffix() -> None:
    assert _iso_utc_to_unix("2024-01-15T10:30:00Z") == 1705314600
    assert _iso_utc_to_unix(None) is None
    assert _iso_utc_to_unix("") is None
    assert _iso_utc_to_unix("garbage") is None


def test_record_is_temporally_eligible_no_run_start_allows_all() -> None:
    assert _record_is_temporally_eligible({}, run_start_unix_seconds=None) is True
    assert _record_is_temporally_eligible(
        {"optimize_end_utc": "2099-01-01T00:00:00Z"}, run_start_unix_seconds=None
    ) is True


def test_record_is_temporally_eligible_rejects_overlapping_fit() -> None:
    # Fit ends 2024-02-15, run starts 2024-02-01 -> overlap -> reject
    assert (
        _record_is_temporally_eligible(
            {"optimize_end_utc": "2024-02-15T00:00:00Z"},
            run_start_unix_seconds=1706745600,  # 2024-02-01
        )
        is False
    )
    # Fit ends 2023-12-01, run starts 2024-02-01 -> no overlap -> allow
    assert (
        _record_is_temporally_eligible(
            {"optimize_end_utc": "2023-12-01T00:00:00Z"},
            run_start_unix_seconds=1706745600,
        )
        is True
    )
    # No optimize_end_utc recorded -> conservatively allow (legacy rows)
    assert (
        _record_is_temporally_eligible(
            {"optimize_end_utc": None},
            run_start_unix_seconds=1706745600,
        )
        is True
    )


def test_resolve_best_sweep_params_skips_overlapping_records() -> None:
    db = _make_db(
        [
            # r1: fit ends 2024-02-15 (overlaps a 2024-02-01 run)
            ("r1", json.dumps({"fast": 5, "slow": 20}), "2024-02-15T00:00:00Z", "2024-02-15T01:00:00Z"),
            # r2: fit ends 2023-12-01 (before the run)
            ("r2", json.dumps({"fast": 3, "slow": 12}), "2023-12-01T00:00:00Z", "2023-12-01T01:00:00Z"),
        ]
    )
    # No guard: latest by created_at -> r1
    params, _ = resolve_best_sweep_params(
        "sma_cross", symbol="BTCUSDT", resolution="60", database_path=db
    )
    assert params == {"fast": 5, "slow": 20}

    # Guard at 2024-02-01: r1 ends 2024-02-15 >= run start -> skip; r2 ends 2023-12-01 -> eligible
    params2, _ = resolve_best_sweep_params(
        "sma_cross",
        symbol="BTCUSDT",
        resolution="60",
        database_path=db,
        run_start_unix_seconds=1706745600,
    )
    assert params2 == {"fast": 3, "slow": 12}


def test_resolve_best_sweep_params_returns_none_when_all_overlap() -> None:
    db = _make_db(
        [
            ("r1", json.dumps({"fast": 5, "slow": 20}), "2024-03-01T00:00:00Z", "2024-03-01T01:00:00Z"),
        ]
    )
    # Run starts 2024-02-01; the only record ends 2024-03-01 -> overlap -> reject
    params, _ = resolve_best_sweep_params(
        "sma_cross",
        symbol="BTCUSDT",
        resolution="60",
        database_path=db,
        run_start_unix_seconds=1706745600,
    )
    assert params is None
