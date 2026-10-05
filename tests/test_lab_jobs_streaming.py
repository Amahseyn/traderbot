from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from lab.store.constants import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
)
from lab.store.database import init_database, open_database


def test_inprocess_job_writes_log(tmp_path: Path):
    from lab.jobs import _run_inprocess_job

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    job_id = "abc123"
    connection.execute(
        """
        INSERT INTO jobs (id, job_type, status, payload_json, log_text, created_at_utc)
        VALUES (?, 'export', 'queued', '{}', '', '2020-01-01T00:00:00+00:00')
        """,
        (job_id,),
    )
    connection.commit()
    connection.close()

    def connection_factory():
        return open_database(database_path)

    def runner() -> None:
        print("line-one")
        print("line-two")

    _run_inprocess_job(connection_factory, job_id, "test", runner)

    connection = open_database(database_path)
    row = connection.execute("SELECT status, log_text FROM jobs WHERE id = ?", (job_id,)).fetchone()
    connection.close()
    assert row["status"] == JOB_STATUS_COMPLETED
    assert "line-one" in row["log_text"]
    assert "line-two" in row["log_text"]


def test_reconcile_orphan_lab_jobs(tmp_path: Path):
    from lab.jobs import ORPHAN_JOB_LOG, reconcile_orphan_lab_jobs

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.execute(
        """
        INSERT INTO jobs (id, job_type, status, payload_json, log_text, created_at_utc)
        VALUES ('run1', 'export', ?, '{}', '', '2020-01-01T00:00:00+00:00')
        """,
        (JOB_STATUS_RUNNING,),
    )
    connection.commit()
    assert reconcile_orphan_lab_jobs(connection) == 1
    row = connection.execute("SELECT status, log_text FROM jobs WHERE id = 'run1'").fetchone()
    connection.close()
    assert row["status"] == JOB_STATUS_FAILED
    assert row["log_text"] == ORPHAN_JOB_LOG


def test_inprocess_job_flushes_task_header_before_runner(tmp_path: Path):
    import threading
    import time

    from lab.jobs import _insert_job, _start_inprocess
    from lab.store.constants import JOB_STATUS_RUNNING

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    job_id = _insert_job(connection, "slow", {})
    connection.close()

    def connection_factory():
        return open_database(database_path)

    started = threading.Event()

    def runner() -> None:
        started.set()
        time.sleep(2.0)

    _start_inprocess(connection_factory, job_id, "slow", runner)
    assert started.wait(timeout=5.0)
    for _ in range(20):
        connection = open_database(database_path)
        row = connection.execute(
            "SELECT status, log_text FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        connection.close()
        if row["status"] == JOB_STATUS_RUNNING and "task: slow" in row["log_text"]:
            return
        time.sleep(0.05)
    raise AssertionError("task header was not flushed while job was running")


def test_stop_queued_lab_job(tmp_path: Path):
    from lab.jobs import _insert_job, stop_lab_job

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    job_id = _insert_job(connection, "export", {"src": "btc"})
    connection.close()

    connection = open_database(database_path)
    result = stop_lab_job(connection, job_id)
    row = connection.execute("SELECT status, log_text FROM jobs WHERE id = ?", (job_id,)).fetchone()
    connection.close()

    assert result["status"] == JOB_STATUS_CANCELLED
    assert row["status"] == JOB_STATUS_CANCELLED
    assert "Stopped while queued" in row["log_text"]


def test_stop_running_lab_job(tmp_path: Path):
    import threading
    import time

    from lab.jobs import _insert_job, _start_inprocess, stop_lab_job

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    job_id = _insert_job(connection, "slow", {})
    connection.close()

    def connection_factory():
        return open_database(database_path)

    finished = threading.Event()

    def runner() -> None:
        for index in range(200):
            print(f"step-{index}")
            time.sleep(0.02)

    def run_job() -> None:
        from lab.jobs import _run_inprocess_job

        _run_inprocess_job(connection_factory, job_id, "slow", runner)
        finished.set()

    thread = threading.Thread(target=run_job, daemon=True)
    thread.start()

    for _ in range(50):
        connection = open_database(database_path)
        row = connection.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        connection.close()
        if row["status"] == JOB_STATUS_RUNNING:
            break
        time.sleep(0.02)
    else:
        raise AssertionError("job did not reach running")

    connection = open_database(database_path)
    result = stop_lab_job(connection, job_id)
    row = connection.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
    connection.close()
    assert result["status"] == JOB_STATUS_CANCELLED
    assert row["status"] == JOB_STATUS_CANCELLED

    assert finished.wait(timeout=10.0)

    connection = open_database(database_path)
    row = connection.execute("SELECT status, log_text FROM jobs WHERE id = ?", (job_id,)).fetchone()
    connection.close()
    assert row["status"] == JOB_STATUS_CANCELLED
    assert "Stopped by user" in row["log_text"]
