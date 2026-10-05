from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.backtesting.engine import BacktestResult
from lab.store.database import init_database, open_database
from lab.store.hooks import record_strategy_backtest


class SyncThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


def test_lab_api_smoke(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    out_dir = tmp_path / "run_out"
    out_dir.mkdir()
    record_strategy_backtest(
        algorithm_for_id("sma_cross", fast=5, slow=20),
        BacktestResult(initial_cash=10_000.0, final_equity=10_100.0, trades=[], equity_curve=[]),
        out_dir=out_dir,
        bars=10,
        summary={"return_pct": 1.0},
        extra={"strategy_id": "sma_cross", "csv": "data/SSVIRT_60.csv"},
        database_path=database_path,
    )

    client = TestClient(create_app(database_path=database_path))

    assert client.get("/health").json()["status"] == "ok"
    assert "market_catalog" in client.get("/health").json()["features"]

    runs = client.get("/api/runs").json()
    assert len(runs) == 1 and runs[0]["run_kind"] == "strategy_backtest"

    assert client.get("/api/runs/missing-id").status_code == 404

    stats = client.get("/api/stats").json()
    assert stats["run_count"] == 1
    assert stats["config_count"] == 1

    configs = client.get("/api/configurations").json()
    assert len(configs) == 1 and configs[0]["config_kind"] == "strategy"


def test_run_artifact_nested_visualizations(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("lab.artifacts.REPO_ROOT", tmp_path)
    from lab.artifacts import artifact_relpath_for_out_dir, resolve_run_artifact

    run_dir = tmp_path / "results" / "strategies" / "runs" / "sma_cross"
    viz_dir = run_dir / "visualizations"
    viz_dir.mkdir(parents=True)
    png_path = viz_dir / "equity_curve.png"
    png_path.write_bytes(b"\x89PNG\r\n")
    summary_path = run_dir / "backtest_summary.json"
    summary_path.write_text("{}", encoding="utf-8")

    repo_relative = str(png_path.relative_to(tmp_path))
    file_query = artifact_relpath_for_out_dir(repo_relative, str(run_dir))
    assert file_query == "visualizations/equity_curve.png"
    assert resolve_run_artifact(str(run_dir), file_query) == png_path.resolve()
    assert resolve_run_artifact(str(run_dir), "results.json") == summary_path.resolve()


def test_lab_api_queues_export_job(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    client = TestClient(create_app(database_path=database_path))

    with patch("lab.jobs.threading.Thread", SyncThread):
        with patch("lab.jobs.run_export_task"):
            response = client.post(
                "/api/jobs/export",
                json={"src": "btc", "dst": "rls", "interval": "60", "days": 1, "out": "data"},
            )
    assert response.status_code == 200
    job_id = response.json()["id"]
    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["job_type"] == "export"
    assert job["status"] in ("queued", "running", "completed")


def test_lab_api_strategy_compare_argv_uses_positional_csv(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app
    from lab.store.catalog import upsert_dataset

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    upsert_dataset(
        connection,
        repo_path="data/BTCIRT_60.csv",
        source="test",
        symbol="BTCIRT",
        resolution="60",
    )
    connection.commit()
    row = connection.execute("SELECT id FROM datasets LIMIT 1").fetchone()
    dataset_id = row["id"]
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    captured: list[tuple[dict, str]] = []

    def fake_compare(body, csv_path):
        captured.append((body, csv_path))

    with patch("lab.jobs.threading.Thread", SyncThread):
        with patch("lab.jobs.run_strategy_compare_task", side_effect=fake_compare):
            response = client.post(
                "/api/jobs/strategy-compare",
                json={"dataset_id": dataset_id, "visualize": True},
            )
    assert response.status_code == 200
    assert captured
    body, csv_path = captured[0]
    assert csv_path == "data/BTCIRT_60.csv"
    assert body.get("visualize") is True
    assert body.get("mode") == "strategies"


def test_lab_api_strategy_compare_passes_simulation_fields(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app
    from lab.store.catalog import upsert_dataset

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    upsert_dataset(
        connection,
        repo_path="data/BTCIRT_60.csv",
        source="test",
        symbol="BTCIRT",
        resolution="60",
    )
    connection.commit()
    dataset_id = connection.execute("SELECT id FROM datasets LIMIT 1").fetchone()["id"]
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    captured: list[tuple[dict, str]] = []

    def fake_compare(body, csv_path):
        captured.append((body, csv_path))

    with patch("lab.jobs.threading.Thread", SyncThread):
        with patch("lab.jobs.run_strategy_compare_task", side_effect=fake_compare):
            response = client.post(
                "/api/jobs/strategy-compare",
                json={
                    "dataset_id": dataset_id,
                    "cash": 5000,
                    "fee": 0.001,
                    "fast": 8,
                    "context_bars": 3,
                },
            )
    assert response.status_code == 200
    body, _ = captured[0]
    assert body.get("cash") == 5000
    assert body.get("fee") == 0.001
    assert body.get("fast") == 8
    assert body.get("context_bars") == 3


def test_lab_api_strategy_jobs_reject_ml_mode_without_forecast(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app
    from lab.store.catalog import upsert_dataset

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    upsert_dataset(
        connection,
        repo_path="data/BTCIRT_60.csv",
        source="test",
        symbol="BTCIRT",
        resolution="60",
    )
    connection.commit()
    dataset_id = connection.execute("SELECT id FROM datasets LIMIT 1").fetchone()["id"]
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    compare = client.post(
        "/api/jobs/strategy-compare",
        json={"dataset_id": dataset_id, "mode": "ml"},
    )
    assert compare.status_code == 400
    test = client.post(
        "/api/jobs/strategy-test",
        json={"dataset_id": dataset_id, "mode": "strategies", "strategy_id": "not-a-strategy"},
    )
    assert test.status_code == 400


def test_lab_api_strategy_test_passes_mode(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app
    from lab.store.catalog import upsert_dataset

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    upsert_dataset(
        connection,
        repo_path="data/BTCIRT_60.csv",
        source="test",
        symbol="BTCIRT",
        resolution="60",
    )
    connection.commit()
    dataset_id = connection.execute("SELECT id FROM datasets LIMIT 1").fetchone()["id"]
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    captured: list[tuple[dict, str]] = []

    def fake_test(body, csv_path):
        captured.append((body, csv_path))

    with patch("lab.jobs.threading.Thread", SyncThread):
        with patch("lab.jobs.run_strategy_test_task", side_effect=fake_test):
            response = client.post(
                "/api/jobs/strategy-test",
                json={"dataset_id": dataset_id, "mode": "strategies", "strategy_id": "sma_cross"},
            )
    assert response.status_code == 200
    body, csv_path = captured[0]
    assert csv_path == "data/BTCIRT_60.csv"
    assert body["mode"] == "strategies"
    assert body["strategy_id"] == "sma_cross"


def test_lab_api_pipeline_job_requires_config_path(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    assert client.post("/api/jobs/pipeline-run-config", json={}).status_code == 400


def test_lab_api_lists_jobs_and_csv_files(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "sample.csv").write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")

    client = TestClient(create_app(database_path=database_path))
    with patch("lab.jobs.threading.Thread", SyncThread):
        with patch("lab.jobs.run_export_task"):
            job_response = client.post(
                "/api/jobs/export",
                json={"src": "btc", "dst": "rls", "interval": "60", "days": 1, "out": "data"},
            )
    job_id = job_response.json()["id"]

    jobs = client.get("/api/jobs").json()
    assert any(row["id"] == job_id for row in jobs)

    from lab.store.catalog import upsert_dataset

    register_connection = open_database(database_path)
    upsert_dataset(
        register_connection,
        repo_path="data/sample.csv",
        source="test",
        symbol="SAMPLE",
        resolution="60",
    )
    register_connection.commit()
    register_connection.close()

    datasets = client.get("/api/datasets").json()
    assert any(row["symbol"] == "SAMPLE" for row in datasets)


def test_lab_api_market_catalog_default_scope(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app
    from lab.store.catalog import ensure_default_jobs_catalog
    from lab.store.database import init_database, open_database

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    ensure_default_jobs_catalog(connection)
    connection.commit()
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    catalog = client.get("/api/data/markets?scope=default_jobs&catalog=true").json()
    assert catalog["total_in_catalog"] >= 1
    assert catalog["markets"][0]["symbol"]


def test_lab_api_pipelines_and_experiment_sync(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app
    from lab.store.database import init_database, open_database

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    pipelines = client.get("/api/pipelines").json()
    pipeline_ids = {row["id"] for row in pipelines}
    assert "crypto-1h-local" in pipeline_ids
    assert "full-research-strategies" in pipeline_ids
    full = next(row for row in pipelines if row["id"] == "full-research-strategies")
    assert full["full"] is True
    export = next(row for row in pipelines if row["id"] == "crypto-jobs-export")
    assert export["full"] is False
    assert [step["id"] for step in export["steps"]] == ["export", "write"]
    assert export["inputs"][0]["key"] == "days"
    hourly = next(row for row in pipelines if row["id"] == "crypto-1h-local")
    hourly_horizon = next(field for field in hourly["inputs"] if field["key"] == "horizon")
    assert hourly_horizon["default"] == "1h"
    assert "1m" not in {option["value"] for option in hourly_horizon["options"]}
    assert client.post("/api/jobs/pipeline-run", json={}).status_code == 400
    assert client.post("/api/jobs/pipeline-run", json={"pipeline_id": "not-a-pipeline"}).status_code == 400
    assert client.post("/api/jobs/custom-research", json={}).status_code == 400
    missing_data = client.post(
        "/api/jobs/custom-research",
        json={"compare_strategies": True, "run_forecasts": False},
    )
    assert missing_data.status_code == 400
    bad_window = client.post(
        "/api/jobs/custom-research",
        json={
            "compare_strategies": True,
            "run_forecasts": False,
            "dataset_ids": ["does-not-exist"],
            "run_start_utc": "2024-01-02T00:00:00Z",
            "run_end_utc": "2024-01-01T00:00:00Z",
        },
    )
    assert bad_window.status_code == 400
    detail = bad_window.text.lower()
    assert "dataset not found" in detail or "run_start_utc" in detail or "before" in detail

    sync = client.post("/api/experiments/sync").json()
    assert sync["registered_count"] >= 2
    experiments = client.get("/api/experiments").json()
    experiment_ids = {row["experiment_id"] for row in experiments}
    assert "crypto-1h-local-all" in experiment_ids
    assert any(row["runnable"] for row in experiments)
