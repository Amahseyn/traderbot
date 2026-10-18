from __future__ import annotations

import json

from lab.store.database import init_database, open_database
from lab.store.discovery import (
    fetch_discovery_run,
    fetch_discovery_run_by_job_id,
    list_discovery_runs,
    record_discovery_run,
)


def test_record_discovery_run_persists_report_json(tmp_path, monkeypatch):
    db_path = tmp_path / "lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))
    connection = open_database(db_path)
    init_database(connection)
    connection.close()

    report = {
        "config": {"scan_kind": "coinbeacon_market", "exchange": "binance-futures"},
        "summary": {"candidates_evaluated": 3, "candidates_eligible": 3, "candidates_rejected": 0},
        "ranked": [{"symbol_key": "ETH", "resolution": "1m", "strategy_id": ""}],
        "screener": {"presets": [{"preset": {"id": "volume-surge"}, "meta": {"matched": 2}}]},
    }
    run_id = record_discovery_run(
        job_id="job-abc",
        body={"screener_presets": ["volume-surge"]},
        report=report,
        artifact_path="results/discovery/job-abc/discovery_report.json",
        finished_at_utc="2026-01-01T00:00:00+00:00",
    )
    assert run_id == "job-abc"

    connection = open_database(db_path)
    try:
        rows = list_discovery_runs(connection, limit=10)
        assert len(rows) == 1
        assert rows[0]["scan_kind"] == "coinbeacon_market"
        assert rows[0]["summary"]["candidates_evaluated"] == 3

        by_id = fetch_discovery_run(connection, "job-abc")
        assert by_id is not None
        assert by_id["report"]["ranked"][0]["symbol_key"] == "ETH"

        by_job = fetch_discovery_run_by_job_id(connection, "job-abc")
        assert by_job is not None
        assert by_job["report"]["screener"]["presets"][0]["meta"]["matched"] == 2

        raw = connection.execute(
            "SELECT report_json FROM discovery_runs WHERE id = ?",
            ("job-abc",),
        ).fetchone()[0]
        assert json.loads(raw)["config"]["scan_kind"] == "coinbeacon_market"
    finally:
        connection.close()


def test_catalog_discovery_run_endpoints(tmp_path, monkeypatch):
    pytest = __import__("pytest")
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    db_path = tmp_path / "lab.db"
    monkeypatch.setenv("TRADERBOT_DB", str(db_path))
    connection = open_database(db_path)
    init_database(connection)
    connection.close()

    record_discovery_run(
        job_id="job-api",
        body={},
        report={
            "config": {"scan_kind": "coinbeacon_market"},
            "summary": {"candidates_evaluated": 1, "candidates_eligible": 1, "candidates_rejected": 0},
            "ranked": [],
        },
        artifact_path=None,
        finished_at_utc="2026-01-01T00:00:00+00:00",
    )

    client = TestClient(create_app(database_path=db_path))
    by_job = client.get("/api/catalog/discovery-runs/by-job/job-api")
    assert by_job.status_code == 200
    assert by_job.json()["report"]["config"]["scan_kind"] == "coinbeacon_market"

    by_id = client.get("/api/catalog/discovery-runs/job-api")
    assert by_id.status_code == 200
    assert by_id.json()["job_id"] == "job-api"
