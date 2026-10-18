from __future__ import annotations

from pathlib import Path

from lab.custom_research import run_custom_research
from lab.store.database import init_database, open_database
from lab.store.queries import fetch_best_sweep


def _write_csv(path: Path, closes: list[float], *, start_ts: int = 0, step_seconds: int = 3600) -> None:
    path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        for index, close in enumerate(closes):
            ts = start_ts + index * step_seconds
            handle.write(f"{ts},{close},{close},{close},{close},1.0\n")


def test_custom_research_optimize_before_compare(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))
    connection = open_database(db_path)
    init_database(connection)
    connection.close()

    csv_path = tmp_path / "BTC_60.csv"
    closes = [100.0 + (index % 12) * 2.5 for index in range(120)]
    _write_csv(csv_path, closes, start_ts=1_700_000_000)

    summary = run_custom_research(
        {
            "compare_strategies": True,
            "optimize_before_compare": True,
            "run_start_unix_seconds": 1_700_000_000 + 80 * 3600,
            "run_end_unix_seconds": 1_700_000_000 + 100 * 3600,
            "strategy_ids": ["sma_cross"],
            "visualize": False,
            "cash": 10_000.0,
            "fee": 0.0,
            "execution": "close",
            "optimize_holdout_tail_bars": 20,
            "optimize_min_trades": 0,
            "dataset_rows": [{"repo_path": str(csv_path)}],
        },
        log=lambda *_args, **_kwargs: None,
    )

    optimize_steps = [step for step in summary["steps"] if step.get("step") == "optimize"]
    assert optimize_steps and optimize_steps[0]["sweeps"] >= 1
    assert summary.get("compare")

    connection = open_database(db_path)
    try:
        best = fetch_best_sweep(connection, strategy_id="sma_cross", symbol="BTC", resolution="60")
    finally:
        connection.close()
    assert best is not None
    assert best.get("best_params")


def test_custom_research_compare_continues_after_file_failure(tmp_path: Path) -> None:
    good_path = tmp_path / "GOOD_60.csv"
    bad_path = tmp_path / "BAD_60.csv"
    closes = [100.0 + (index % 8) for index in range(80)]
    _write_csv(good_path, closes, start_ts=1_700_000_000)
    bad_path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")

    logs: list[str] = []

    summary = run_custom_research(
        {
            "compare_strategies": True,
            "strategy_ids": ["sma_cross"],
            "visualize": False,
            "cash": 10_000.0,
            "fee": 0.0,
            "execution": "close",
            "dataset_rows": [
                {"repo_path": str(good_path)},
                {"repo_path": str(bad_path)},
            ],
        },
        log=lambda message, **_kwargs: logs.append(str(message)),
    )

    compare_rows = summary.get("compare") or []
    assert any(not row.get("skipped") for row in compare_rows)
    assert any(row.get("skipped") for row in compare_rows)
    assert any("BAD_60.csv" in line and "compare failed" in line for line in logs)


def test_custom_research_optimize_without_run_start_auto_splits(tmp_path: Path, monkeypatch) -> None:
    """Reported regression: optimize before compare with no usable run_start must not fail."""
    db_path = tmp_path / "lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))
    connection = open_database(db_path)
    init_database(connection)
    connection.close()

    csv_path = tmp_path / "BRETTUSDT_1.csv"
    closes = [100.0 + (index % 12) * 2.5 for index in range(200)]
    _write_csv(csv_path, closes, start_ts=1_700_000_000, step_seconds=60)

    logs: list[str] = []
    summary = run_custom_research(
        {
            "compare_strategies": True,
            "optimize_before_compare": True,
            "strategy_ids": ["sma_cross"],
            "visualize": False,
            "cash": 10_000.0,
            "fee": 0.0,
            "execution": "close",
            "optimize_holdout_tail_bars": 20,
            "optimize_min_trades": 0,
            "dataset_rows": [{"repo_path": str(csv_path)}],
        },
        log=lambda message, **_kwargs: logs.append(str(message)),
    )

    optimize_rows = summary.get("optimize") or []
    assert optimize_rows and optimize_rows[0]["auto_split"] is True
    assert optimize_rows[0]["train_bars"] >= 40
    assert any("auto walk-forward split" in line for line in logs)
    assert summary.get("compare")

    connection = open_database(db_path)
    try:
        best = fetch_best_sweep(connection, strategy_id="sma_cross", symbol="BRETTUSDT", resolution="1")
    finally:
        connection.close()
    assert best is not None
    assert best.get("best_params")
