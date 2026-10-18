from __future__ import annotations

from pathlib import Path

import pytest

from lab.job_resolvers import (
    JobPayloadError,
    resolve_custom_research_body,
    validate_terminal_job_body,
)
from lab.store.database import init_database, open_database
from traderbot.backtesting.research_windows import (
    MIN_COMPARE_EVAL_BARS,
    MIN_OPTIMIZER_TRAIN_BARS,
    ResearchWindowError,
    derive_walk_forward_run_start,
    load_research_bar_windows,
    validate_research_optimizer_windows,
)


def _write_csv(path: Path, count: int, *, start_ts: int = 0, step_seconds: int = 3600) -> None:
    path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        for index in range(count):
            ts = start_ts + index * step_seconds
            price = 100.0 + index * 0.1
            handle.write(f"{ts},{price},{price},{price},{price},1.0\n")


def test_optimizer_train_bars_end_before_compare_start(tmp_path: Path) -> None:
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, 120, start_ts=1_700_000_000)
    body = {
        "optimize_before_compare": True,
        "run_start_unix_seconds": 1_700_000_000 + 80 * 3600,
        "run_end_unix_seconds": 1_700_000_000 + 100 * 3600,
    }
    windows = load_research_bar_windows(csv_path, body, None)
    assert len(windows.train_bars) == 80
    assert len(windows.eval_bars) == 20
    assert windows.symbol == "BTC"
    assert windows.resolution == "60"
    # A usable explicit start is honored, not replaced by an auto split.
    assert windows.auto_split is False
    assert windows.run_start_unix_seconds == 1_700_000_000 + 80 * 3600
    last_train_close = int(windows.train_bars[-1]["timestamp"]) + 3600
    first_eval_open = int(windows.eval_bars[0]["timestamp"])
    assert last_train_close <= first_eval_open


def test_auto_split_when_run_start_missing(tmp_path: Path) -> None:
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, 100, start_ts=1_700_000_000)
    windows = load_research_bar_windows(csv_path, {"optimize_before_compare": True}, None)
    assert windows.auto_split is True
    assert windows.run_start_unix_seconds is not None
    assert len(windows.train_bars) >= MIN_OPTIMIZER_TRAIN_BARS
    assert len(windows.eval_bars) >= MIN_COMPARE_EVAL_BARS
    assert len(windows.train_bars) + len(windows.eval_bars) == 100
    last_train_close = int(windows.train_bars[-1]["timestamp"]) + 3600
    first_eval_open = int(windows.eval_bars[0]["timestamp"])
    assert last_train_close <= first_eval_open


def test_auto_split_when_run_start_after_all_bars(tmp_path: Path) -> None:
    """Explicit run_start after the file (common when UI date > last candle) used to yield 0 eval bars."""
    csv_path = tmp_path / "TRXUSDT_1.csv"
    _write_csv(csv_path, 500, start_ts=1_792_110_840, step_seconds=60)
    last_open = 1_792_110_840 + 499 * 60
    body = {
        "optimize_before_compare": True,
        "run_start_unix_seconds": last_open + 3600,
    }
    windows = load_research_bar_windows(csv_path, body, None)
    assert windows.auto_split is True
    assert len(windows.train_bars) >= MIN_OPTIMIZER_TRAIN_BARS
    assert len(windows.eval_bars) >= MIN_COMPARE_EVAL_BARS


def test_auto_split_when_run_start_leaves_no_leading_bars(tmp_path: Path) -> None:
    """The reported failure: run_start at the first bar used to raise with 0 train bars."""
    csv_path = tmp_path / "BRETTUSDT_1.csv"
    _write_csv(csv_path, 500, start_ts=1_700_000_000, step_seconds=60)
    body = {
        "optimize_before_compare": True,
        "run_start_unix_seconds": 1_700_000_000,
    }
    windows = load_research_bar_windows(csv_path, body, None)
    assert windows.auto_split is True
    assert len(windows.train_bars) >= MIN_OPTIMIZER_TRAIN_BARS
    assert len(windows.eval_bars) >= MIN_COMPARE_EVAL_BARS


def test_file_too_short_for_optimizer_raises(tmp_path: Path) -> None:
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, MIN_OPTIMIZER_TRAIN_BARS - 10, start_ts=1_700_000_000)
    with pytest.raises(ResearchWindowError, match="at least"):
        load_research_bar_windows(csv_path, {"optimize_before_compare": True}, None)


def test_allow_full_history_optimize_keeps_full_train(tmp_path: Path) -> None:
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, 100, start_ts=1_700_000_000)
    windows = load_research_bar_windows(
        csv_path,
        {"optimize_before_compare": True, "allow_full_history_optimize": True},
        None,
    )
    assert windows.auto_split is False
    assert len(windows.train_bars) == 100
    assert len(windows.eval_bars) == 100


def test_derive_walk_forward_run_start_respects_floor() -> None:
    bars = [{"timestamp": 1_000 + index * 60} for index in range(50)]
    run_start = derive_walk_forward_run_start(bars)
    assert run_start == bars[40]["timestamp"]


def test_derive_walk_forward_run_start_none_when_too_short() -> None:
    bars = [{"timestamp": index * 60} for index in range(MIN_OPTIMIZER_TRAIN_BARS)]
    assert derive_walk_forward_run_start(bars) is None


def test_resolve_custom_research_allows_optimize_without_start(tmp_path: Path) -> None:
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, 120)
    db = tmp_path / "lab.db"
    connection = open_database(db)
    init_database(connection)
    from lab.store.catalog import upsert_dataset

    upsert_dataset(connection, repo_path=str(csv_path), source="test")
    connection.commit()
    try:
        dataset_id = connection.execute("SELECT id FROM datasets LIMIT 1").fetchone()[0]
        prepared = resolve_custom_research_body(
            connection,
            {
                "compare_strategies": True,
                "optimize_before_compare": True,
                "dataset_ids": [dataset_id],
            },
        )
    finally:
        connection.close()
    # No start is required: the per-file walk-forward split is derived later.
    assert "run_start_unix_seconds" not in prepared
    assert prepared["optimize_before_compare"] is True


def test_terminal_rejects_run_dates_with_optimize_before_run() -> None:
    with pytest.raises(JobPayloadError, match="optimize_before_run"):
        validate_terminal_job_body(
            {
                "optimize_before_run": True,
                "run_start_utc": "2024-01-01T00:00:00Z",
                "strategy": "sma_cross",
            },
        )


def test_optimize_without_run_start_is_allowed() -> None:
    # Missing start no longer raises; each file gets an automatic split.
    assert validate_research_optimizer_windows({"optimize_before_compare": True}) is None


def test_optimize_rejects_start_at_or_after_end() -> None:
    body = {
        "optimize_before_compare": True,
        "run_start_unix_seconds": 2_000,
        "run_end_unix_seconds": 1_000,
    }
    with pytest.raises(ResearchWindowError, match="before"):
        validate_research_optimizer_windows(body)
