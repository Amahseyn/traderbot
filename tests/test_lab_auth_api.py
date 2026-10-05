from __future__ import annotations

from pathlib import Path

import pytest

from lab.store.database import init_database, open_database


def test_lab_api_auth_status(tmp_path: Path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    health = client.get("/health").json()
    assert "auth_api" in health["features"]

    status = client.get("/api/auth/status").json()
    assert "api_keys_configured" in status
    assert "auth_token_configured" in status
