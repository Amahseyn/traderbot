from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from lab.store.database import open_database


def _parse_json_field(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _row_to_summary_dict(row: sqlite3.Row, *, include_report: bool) -> dict[str, Any]:
    item = dict(row)
    for key in ("config_json", "summary_json"):
        raw = item.pop(key, None)
        parsed = _parse_json_field(raw)
        item[key.replace("_json", "")] = parsed
    report_raw = item.pop("report_json", None)
    if include_report and report_raw:
        item["report"] = _parse_json_field(report_raw)
    config = item.get("config")
    if isinstance(config, dict):
        item["scan_kind"] = config.get("scan_kind")
    return item


def record_discovery_run(
    *,
    job_id: str | None,
    body: dict[str, Any],
    report: dict[str, Any],
    artifact_path: str | None,
    finished_at_utc: str,
) -> str:
    run_id = job_id or str(uuid.uuid4())
    summary = report.get("summary") or {}
    report_config = report.get("config") if isinstance(report.get("config"), dict) else {}
    exchange = str(
        body.get("exchange") or report_config.get("exchange") or "binance-futures",
    )
    stored_config = dict(body)
    stored_config.update(report_config)
    params = (
        run_id,
        job_id,
        exchange,
        "completed",
        json.dumps(stored_config),
        json.dumps(summary),
        artifact_path,
        json.dumps(report),
        finished_at_utc,
        finished_at_utc,
    )
    sql = """
        INSERT INTO discovery_runs (
            id, job_id, exchange, status, config_json, summary_json,
            artifact_path, report_json, created_at_utc, finished_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            status = excluded.status,
            summary_json = excluded.summary_json,
            artifact_path = excluded.artifact_path,
            report_json = excluded.report_json,
            finished_at_utc = excluded.finished_at_utc
    """
    for attempt in range(5):
        connection = open_database()
        try:
            connection.execute(sql, params)
            connection.commit()
            break
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))
        finally:
            connection.close()
    return run_id


def list_discovery_runs(connection, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT id, job_id, exchange, status, config_json, summary_json,
               artifact_path, created_at_utc, finished_at_utc
        FROM discovery_runs
        ORDER BY finished_at_utc DESC, created_at_utc DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_row_to_summary_dict(row, include_report=False) for row in rows]


def fetch_discovery_run(connection, run_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT id, job_id, exchange, status, config_json, summary_json,
               artifact_path, report_json, created_at_utc, finished_at_utc
        FROM discovery_runs
        WHERE id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_summary_dict(row, include_report=True)


def fetch_discovery_run_by_job_id(connection, job_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT id, job_id, exchange, status, config_json, summary_json,
               artifact_path, report_json, created_at_utc, finished_at_utc
        FROM discovery_runs
        WHERE job_id = ?
        ORDER BY finished_at_utc DESC
        LIMIT 1
        """,
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_summary_dict(row, include_report=True)
