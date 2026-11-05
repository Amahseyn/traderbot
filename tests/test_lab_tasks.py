from __future__ import annotations

from pathlib import Path

from lab.custom_research import run_custom_research
from lab.store.database import init_database, open_database
from lab.store.queries import list_evaluation_runs, list_sweep_sessions
from lab.tasks import (
    run_strategy_compare_task,
    run_strategy_sweep_task,
    run_strategy_test_task,
)


def _write_sample_csv(path: Path, bar_count: int = 60, *, start_ts: int = 1_700_000_000) -> None:
    path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        for index in range(bar_count):
            ts = start_ts + index * 60
            close = 100.0 + (index % 10) * 1.5
            handle.write(f"{ts},{close},{close + 1},{close - 1},{close},10.0\n")


def test_strategy_test_task_creates_unique_runs_on_same_dataset(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))
    connection = open_database(db_path)
    init_database(connection)
    connection.close()

    csv_path = tmp_path / "BTCIRT_1.csv"
    _write_sample_csv(csv_path)

    body = {
        "strategy_id": "sma_cross",
        "visualize": False,
        "cash": 10_000.0,
    }

    # Run first time
    run_strategy_test_task(body, str(csv_path))

    connection = open_database(db_path)
    try:
        runs_1 = list_evaluation_runs(connection, strategy_id="sma_cross", symbol="BTCIRT")
        assert len(runs_1) == 1
        assert runs_1[0].data_context.get("optimizer_enabled") is True
        assert "fast" in runs_1[0].parameters
        out_dir_1 = runs_1[0].out_dir
    finally:
        connection.close()

    # Run second time on the same dataset
    run_strategy_test_task(body, str(csv_path))

    connection = open_database(db_path)
    try:
        runs_2 = list_evaluation_runs(connection, strategy_id="sma_cross", symbol="BTCIRT")
        assert len(runs_2) == 2, f"Expected 2 runs, got {len(runs_2)} (run was replaced instead of appended)"
        assert runs_2[0].id != runs_2[1].id
        assert runs_2[0].out_dir != runs_2[1].out_dir
        assert out_dir_1 in (runs_2[0].out_dir, runs_2[1].out_dir)
    finally:
        connection.close()


def test_strategy_compare_task_creates_unique_runs_on_same_dataset(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))
    connection = open_database(db_path)
    init_database(connection)
    connection.close()

    csv_path = tmp_path / "ETHIRT_1.csv"
    _write_sample_csv(csv_path)

    body = {
        "strategy_ids": ["sma_cross"],
        "visualize": False,
        "cash": 10_000.0,
    }

    # Run first time
    run_strategy_compare_task(body, str(csv_path))

    connection = open_database(db_path)
    try:
        runs_1 = list_evaluation_runs(connection, strategy_id="sma_cross", symbol="ETHIRT")
        assert len(runs_1) == 1
    finally:
        connection.close()

    # Run second time on the same dataset
    run_strategy_compare_task(body, str(csv_path))

    connection = open_database(db_path)
    try:
        runs_2 = list_evaluation_runs(connection, strategy_id="sma_cross", symbol="ETHIRT")
        assert len(runs_2) == 2, f"Expected 2 runs, got {len(runs_2)} (compare run was replaced)"
        assert runs_2[0].id != runs_2[1].id
        assert runs_2[0].out_dir != runs_2[1].out_dir
    finally:
        connection.close()


def test_custom_research_preserves_multiple_runs_on_same_dataset(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))
    connection = open_database(db_path)
    init_database(connection)
    connection.close()

    csv_path = tmp_path / "SOLIRT_1.csv"
    _write_sample_csv(csv_path)

    body = {
        "compare_strategies": True,
        "strategy_ids": ["sma_cross"],
        "visualize": False,
        "cash": 10_000.0,
        "dataset_rows": [{"repo_path": str(csv_path)}],
    }

    run_custom_research(body, log=lambda *_args, **_kwargs: None)
    run_custom_research(body, log=lambda *_args, **_kwargs: None)

    connection = open_database(db_path)
    try:
        runs = list_evaluation_runs(connection, strategy_id="sma_cross", symbol="SOLIRT")
        assert len(runs) == 2, f"Expected 2 runs from custom research, got {len(runs)}"
        assert runs[0].id != runs[1].id
        assert runs[0].out_dir != runs[1].out_dir
    finally:
        connection.close()


def test_strategy_sweep_task_creates_unique_sweeps_on_same_dataset(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))
    connection = open_database(db_path)
    init_database(connection)
    connection.close()

    csv_path = tmp_path / "ADAIRT_1.csv"
    _write_sample_csv(csv_path)

    body = {
        "strategy_id": "sma_cross",
        "cash": 10_000.0,
        "optimize_min_trades": 0,
        "param_grid": {"fast": [3, 5], "slow": [10, 15]},
    }

    run_strategy_sweep_task(body, str(csv_path))
    run_strategy_sweep_task(body, str(csv_path))

    connection = open_database(db_path)
    try:
        sweeps = list_sweep_sessions(connection, strategy_id="sma_cross", symbol="ADAIRT")
        assert len(sweeps) == 2, f"Expected 2 sweeps, got {len(sweeps)}"
        assert sweeps[0]["id"] != sweeps[1]["id"]
        assert sweeps[0]["manifest_path"] != sweeps[1]["manifest_path"]
    finally:
        connection.close()


def test_explicit_out_dir_is_respected(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))
    connection = open_database(db_path)
    init_database(connection)
    connection.close()

    csv_path = tmp_path / "XRPIRT_1.csv"
    _write_sample_csv(csv_path)

    custom_out = tmp_path / "custom_fixed_run_out"
    body = {
        "strategy_id": "sma_cross",
        "visualize": False,
        "cash": 10_000.0,
        "out": str(custom_out),
    }

    run_strategy_test_task(body, str(csv_path))

    connection = open_database(db_path)
    try:
        runs = list_evaluation_runs(connection, strategy_id="sma_cross", symbol="XRPIRT")
        assert len(runs) == 1
        assert runs[0].out_dir == str(custom_out / "runs" / "sma_cross")
    finally:
        connection.close()


def test_api_runs_returns_optimizer_status_and_parameters(tmp_path: Path, monkeypatch) -> None:
    from fastapi.testclient import TestClient
    from lab.app import create_app

    db_path = tmp_path / "lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))
    connection = open_database(db_path)
    init_database(connection)
    connection.close()

    csv_path = tmp_path / "LTCIRT_1.csv"
    _write_sample_csv(csv_path)

    body = {
        "strategy_id": "sma_cross",
        "visualize": False,
        "cash": 10_000.0,
        "use_optimized_strategy_params": True,
    }
    run_strategy_test_task(body, str(csv_path))

    client = TestClient(create_app(database_path=db_path))
    runs = client.get("/api/runs").json()
    assert len(runs) >= 1
    run = runs[0]
    assert run["optimizer_enabled"] is True
    assert isinstance(run["parameters"], dict)
    assert "fast" in run["parameters"]
