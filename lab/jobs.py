from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from lab.store.constants import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
)
from lab.job_control import (
    JobStoppedError,
    job_worker_active,
    register_job_cancel,
    register_job_worker,
    request_job_cancel,
    unregister_job_cancel,
    unregister_job_worker,
)
from lab.job_resolvers import (
    JobPayloadError,
    apply_strategy_mode,
    resolve_config_path_from_body,
    resolve_csv_from_body,
    resolve_pipeline_run_body,
    resolve_custom_research_body,
    resolve_export_argv_fields,
    resolve_sweep_body,
)
from lab.task_log import CancellableJobLogWriter
from lab.tasks import (
    run_export_task,
    run_named_pipeline_task,
    run_pipeline_config_task,
    run_strategy_compare_task,
    run_strategy_sweep_task,
    run_strategy_test_task,
    run_custom_research_task,
)
from lab.terminal_tasks import (
    run_terminal_live_task,
    run_terminal_once_task,
    run_terminal_replay_task,
)
from lab.store.catalog import expected_export_repo_path, upsert_dataset


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _insert_job(connection, job_type: str, payload: dict[str, Any]) -> str:
    job_id = uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO jobs (id, job_type, status, payload_json, log_text, created_at_utc)
        VALUES (?, ?, ?, ?, '', ?)
        """,
        (job_id, job_type, JOB_STATUS_QUEUED, json.dumps(payload), _utc_now()),
    )
    connection.commit()
    return job_id


def _update_job(
    connection,
    job_id: str,
    *,
    status: str,
    log_text: str | None = None,
    finished: bool = False,
) -> None:
    if finished and status in (JOB_STATUS_COMPLETED, JOB_STATUS_FAILED):
        connection.execute(
            """
            UPDATE jobs SET status = ?, log_text = COALESCE(?, log_text), finished_at_utc = ?
            WHERE id = ? AND status != ?
            """,
            (status, log_text, _utc_now(), job_id, JOB_STATUS_CANCELLED),
        )
    elif finished:
        connection.execute(
            """
            UPDATE jobs SET status = ?, log_text = COALESCE(?, log_text), finished_at_utc = ?
            WHERE id = ?
            """,
            (status, log_text, _utc_now(), job_id),
        )
    else:
        connection.execute(
            "UPDATE jobs SET status = ?, log_text = COALESCE(?, log_text) WHERE id = ?",
            (status, log_text, job_id),
        )
    connection.commit()


def list_jobs(connection, limit: int = 50) -> list[dict[str, Any]]:
    capped = min(max(limit, 1), 200)
    rows = connection.execute(
        "SELECT * FROM jobs ORDER BY created_at_utc DESC LIMIT ?",
        (capped,),
    ).fetchall()
    jobs = [_job_row_dict(row) for row in rows]
    return [
        _reconcile_stale_running_job(connection, job["id"], job) for job in jobs
    ]


ORPHAN_JOB_LOG = (
    "[lab] Job interrupted — the Lab API restarted (or was replaced) while this job was "
    "in progress. Start the job again to see live logs.\n"
)


def reconcile_orphan_lab_jobs(connection) -> int:
    """Mark queued/running jobs failed on API startup (in-process workers are gone)."""
    cursor = connection.execute(
        """
        UPDATE jobs
        SET status = ?, log_text = ?, finished_at_utc = ?
        WHERE status IN (?, ?)
        """,
        (
            JOB_STATUS_FAILED,
            ORPHAN_JOB_LOG,
            _utc_now(),
            JOB_STATUS_QUEUED,
            JOB_STATUS_RUNNING,
        ),
    )
    connection.commit()
    return int(cursor.rowcount)


def _job_row_dict(row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "job_type": row["job_type"],
        "status": row["status"],
        "payload": json.loads(row["payload_json"]),
        "log_text": row["log_text"],
        "created_at_utc": row["created_at_utc"],
        "finished_at_utc": row["finished_at_utc"],
    }


def _reconcile_stale_running_job(connection, job_id: str, row: dict[str, Any]) -> dict[str, Any]:
    if row["status"] != JOB_STATUS_RUNNING:
        return row
    if job_worker_active(job_id):
        return row
    log_text = (row.get("log_text") or "") + ORPHAN_JOB_LOG
    _update_job(connection, job_id, status=JOB_STATUS_FAILED, log_text=log_text, finished=True)
    refreshed = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if refreshed is None:
        return row
    return _job_row_dict(refreshed)


def _fetch_job(connection, job_id: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        return None
    job = _job_row_dict(row)
    return _reconcile_stale_running_job(connection, job_id, job)


def _run_inprocess_job(
    connection_factory: Callable,
    job_id: str,
    task_name: str,
    runner: Callable[[], None],
    *,
    on_success=None,
) -> None:
    cancel_event = register_job_cancel(job_id)
    register_job_worker(job_id)
    connection = connection_factory()
    writer = CancellableJobLogWriter(connection_factory, job_id, cancel_event)
    try:
        cursor = connection.execute(
            "UPDATE jobs SET status = ? WHERE id = ? AND status = ?",
            (JOB_STATUS_RUNNING, job_id, JOB_STATUS_QUEUED),
        )
        connection.commit()
        if cursor.rowcount == 0:
            row = _fetch_job(connection, job_id)
            connection.close()
            if row is None or row["status"] != JOB_STATUS_RUNNING:
                return
        else:
            connection.close()
        writer.write(f"task: {task_name}\n")
        writer.flush()
        from contextlib import redirect_stderr, redirect_stdout

        with redirect_stdout(writer), redirect_stderr(writer):
            runner()
        writer.flush()
        log_text = writer.getvalue()
        connection = connection_factory()
        if on_success is not None:
            on_success(connection)
        _update_job(connection, job_id, status=JOB_STATUS_COMPLETED, log_text=log_text, finished=True)
    except JobStoppedError:
        log_text = f"{writer.getvalue()}\n[lab] Stopped by user.\n"
        connection = connection_factory()
        _update_job(connection, job_id, status=JOB_STATUS_CANCELLED, log_text=log_text, finished=True)
    except Exception as exc:
        writer.write(f"\n[lab] {exc}\n")
        writer.flush()
        log_text = writer.getvalue()
        connection = connection_factory()
        _update_job(connection, job_id, status=JOB_STATUS_FAILED, log_text=log_text, finished=True)
    finally:
        unregister_job_cancel(job_id)
        unregister_job_worker(job_id)
        try:
            connection.close()
        except Exception:
            pass


def stop_lab_job(connection, job_id: str) -> dict[str, Any]:
    """Stop a queued or running in-process Lab job."""
    row = _fetch_job(connection, job_id)
    if row is None:
        raise ValueError("job not found")
    status = row["status"]
    if status not in (JOB_STATUS_QUEUED, JOB_STATUS_RUNNING):
        raise ValueError("job is not active")

    if status == JOB_STATUS_QUEUED:
        log_text = (row.get("log_text") or "") + "[lab] Stopped while queued.\n"
        _update_job(
            connection,
            job_id,
            status=JOB_STATUS_CANCELLED,
            log_text=log_text,
            finished=True,
        )
        return {"id": job_id, "status": JOB_STATUS_CANCELLED}

    request_job_cancel(job_id)
    existing_log = row.get("log_text") or ""
    if "[lab] Stopped by user." not in existing_log:
        existing_log += "[lab] Stopped by user.\n"
    _update_job(
        connection,
        job_id,
        status=JOB_STATUS_CANCELLED,
        log_text=existing_log,
        finished=True,
    )
    return {"id": job_id, "status": JOB_STATUS_CANCELLED, "stop_requested": True}


def _start_inprocess(
    connection_factory: Callable,
    job_id: str,
    task_name: str,
    runner: Callable[[], None],
    *,
    on_success=None,
) -> None:
    thread = threading.Thread(
        target=_run_inprocess_job,
        args=(connection_factory, job_id, task_name),
        kwargs={"runner": runner, "on_success": on_success},
        daemon=True,
    )
    thread.start()


def register_job_routes(app, get_connection: Callable) -> None:
    from fastapi import HTTPException, Query

    @app.get("/api/jobs")
    def list_jobs_route(limit: int = Query(default=50, le=200)):
        connection = get_connection()
        try:
            return list_jobs(connection, limit=limit)
        finally:
            connection.close()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        connection = get_connection()
        try:
            row = _fetch_job(connection, job_id)
        finally:
            connection.close()
        if row is None:
            raise HTTPException(status_code=404, detail="job not found")
        return row

    @app.post("/api/jobs/{job_id}/stop")
    def stop_job(job_id: str):
        connection = get_connection()
        try:
            try:
                result = stop_lab_job(connection, job_id)
            except ValueError as exc:
                detail = str(exc)
                if detail == "job not found":
                    raise HTTPException(status_code=404, detail=detail) from exc
                raise HTTPException(status_code=400, detail=detail) from exc
        finally:
            connection.close()
        return result

    @app.post("/api/jobs/export")
    def job_export(body: dict[str, Any]):
        connection = get_connection()
        try:
            fields = resolve_export_argv_fields(connection, body)
        except JobPayloadError as exc:
            connection.close()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            job_id = _insert_job(connection, "export", body)
        finally:
            connection.close()

        def on_export_success(connection) -> None:
            src = fields.get("src")
            dst = fields.get("dst")
            interval = fields.get("interval")
            if not src or not dst or not interval:
                return
            from traderbot.markets.market_data import market_symbol

            symbol = market_symbol(str(src), str(dst))
            output_dir = str(fields.get("out") or "data")
            repo_path = expected_export_repo_path(symbol=symbol, interval=str(interval), output_dir=output_dir)
            upsert_dataset(
                connection,
                repo_path=repo_path,
                source="export_job",
                symbol=symbol,
                resolution=str(interval),
            )
            connection.commit()

        _start_inprocess(
            get_connection,
            job_id,
            "export",
            lambda: run_export_task(fields),
            on_success=on_export_success,
        )
        return {"id": job_id, "status": JOB_STATUS_QUEUED}

    @app.post("/api/jobs/strategy-compare")
    def job_strategy_compare(body: dict[str, Any]):
        connection = get_connection()
        try:
            csv_path = resolve_csv_from_body(connection, body)
            body = apply_strategy_mode(connection, body, strategy_required=False)
        except JobPayloadError as exc:
            connection.close()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            job_id = _insert_job(connection, "strategy-compare", body)
        finally:
            connection.close()
        _start_inprocess(
            get_connection,
            job_id,
            "strategy-compare",
            lambda: run_strategy_compare_task(body, csv_path),
        )
        return {"id": job_id, "status": JOB_STATUS_QUEUED}

    @app.post("/api/jobs/strategy-test")
    def job_strategy_test(body: dict[str, Any]):
        connection = get_connection()
        try:
            csv_path = resolve_csv_from_body(connection, body)
            body = apply_strategy_mode(connection, body, strategy_required=True)
        except JobPayloadError as exc:
            connection.close()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            job_id = _insert_job(connection, "strategy-test", body)
        finally:
            connection.close()
        _start_inprocess(
            get_connection,
            job_id,
            "strategy-test",
            lambda: run_strategy_test_task(body, csv_path),
        )
        return {"id": job_id, "status": JOB_STATUS_QUEUED}

    @app.post("/api/jobs/strategy-sweep")
    def job_strategy_sweep(body: dict[str, Any]):
        connection = get_connection()
        try:
            prepared = resolve_sweep_body(connection, body)
            csv_path = str(prepared.pop("csv"))
        except JobPayloadError as exc:
            connection.close()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            job_id = _insert_job(connection, "strategy-sweep", prepared)
        finally:
            connection.close()
        _start_inprocess(
            get_connection,
            job_id,
            "strategy-sweep",
            lambda: run_strategy_sweep_task(prepared, csv_path),
        )
        return {"id": job_id, "status": JOB_STATUS_QUEUED}

    @app.post("/api/jobs/pipeline-run-config")
    def job_pipeline_run_config(body: dict[str, Any]):
        connection = get_connection()
        try:
            config_path = resolve_config_path_from_body(connection, body)
        except JobPayloadError as exc:
            connection.close()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            job_id = _insert_job(connection, "pipeline-run-config", body)
        finally:
            connection.close()
        _start_inprocess(
            get_connection,
            job_id,
            "pipeline-run-config",
            lambda: run_pipeline_config_task(
                config_path,
                param_overrides=body.get("params") if isinstance(body.get("params"), dict) else None,
                step_param_overrides=body.get("step_params") if isinstance(body.get("step_params"), dict) else None,
            ),
        )
        return {"id": job_id, "status": JOB_STATUS_QUEUED}

    @app.post("/api/jobs/pipeline-run")
    def job_pipeline_run(body: dict[str, Any]):
        connection = get_connection()
        try:
            prepared = resolve_pipeline_run_body(connection, body)
        except JobPayloadError as exc:
            connection.close()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            job_id = _insert_job(connection, "pipeline-run", prepared)
        finally:
            connection.close()
        _start_inprocess(
            get_connection,
            job_id,
            "pipeline-run",
            lambda: run_named_pipeline_task(prepared),
        )
        return {"id": job_id, "status": JOB_STATUS_QUEUED}

    @app.post("/api/jobs/custom-research")
    def job_custom_research(body: dict[str, Any]):
        connection = get_connection()
        try:
            prepared = resolve_custom_research_body(connection, body)
        except JobPayloadError as exc:
            connection.close()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            job_id = _insert_job(connection, "custom-research", prepared)
        finally:
            connection.close()
        _start_inprocess(
            get_connection,
            job_id,
            "custom-research",
            lambda: run_custom_research_task(prepared),
        )
        return {"id": job_id, "status": JOB_STATUS_QUEUED}

    @app.post("/api/jobs/terminal-once")
    def job_terminal_once(body: dict[str, Any]):
        connection = get_connection()
        try:
            job_id = _insert_job(connection, "terminal-once", body)
        finally:
            connection.close()
        _start_inprocess(
            get_connection,
            job_id,
            "terminal-once",
            lambda: run_terminal_once_task(body),
        )
        return {"id": job_id, "status": JOB_STATUS_QUEUED}

    @app.post("/api/jobs/terminal-replay")
    def job_terminal_replay(body: dict[str, Any]):
        connection = get_connection()
        try:
            csv_path = resolve_csv_from_body(connection, body)
        except JobPayloadError as exc:
            connection.close()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        try:
            job_id = _insert_job(connection, "terminal-replay", body)
        finally:
            connection.close()
        _start_inprocess(
            get_connection,
            job_id,
            "terminal-replay",
            lambda: run_terminal_replay_task(body, csv_path),
        )
        return {"id": job_id, "status": JOB_STATUS_QUEUED}

    @app.post("/api/jobs/terminal-live")
    def job_terminal_live(body: dict[str, Any]):
        connection = get_connection()
        try:
            job_id = _insert_job(connection, "terminal-live", body)
        finally:
            connection.close()
        task_body = {**body, "job_id": job_id}
        _start_inprocess(
            get_connection,
            job_id,
            "terminal-live",
            lambda: run_terminal_live_task(task_body),
        )
        return {"id": job_id, "status": JOB_STATUS_QUEUED}
