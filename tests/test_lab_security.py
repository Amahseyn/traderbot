from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lab.store.database import init_database, open_database
class _SyncThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


def test_lab_api_requires_token_for_mutations(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import lab.security as lab_security
    from lab.app import create_app

    monkeypatch.delenv("LAB_API_DISABLE_AUTH", raising=False)
    monkeypatch.setenv("LAB_API_TOKEN", "secret-test-token")
    lab_security._TOKEN = None

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    assert client.get("/health").status_code == 200
    assert client.post("/api/jobs/export", json={"src": "btc", "dst": "rls", "interval": "60"}).status_code == 401
    headers = {"Authorization": "Bearer secret-test-token"}
    with patch("lab.jobs.threading.Thread", _SyncThread):
        with patch("lab.jobs.run_export_task"):
            response = client.post(
                "/api/jobs/export",
                json={"src": "btc", "dst": "rls", "interval": "60", "days": 1, "out": "data"},
                headers=headers,
            )
    assert response.status_code == 200


def test_lab_api_risk_limits_validated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    import lab.security as lab_security

    monkeypatch.delenv("LAB_API_DISABLE_AUTH", raising=False)
    monkeypatch.setenv("LAB_API_TOKEN", "secret-test-token")
    lab_security._TOKEN = None

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    headers = {"Authorization": "Bearer secret-test-token"}
    response = client.post(
        "/api/risk/limits",
        headers=headers,
        json={"capital_cap": -1},
    )
    assert response.status_code == 400
