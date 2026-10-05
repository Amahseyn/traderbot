from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lab.store.canonical import content_hash_for_configuration


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def upsert_configuration(
    connection: sqlite3.Connection,
    *,
    config_kind: str,
    strategy_id: str | None,
    model_id: str | None,
    symbol: str | None,
    resolution: str | None,
    horizon_label: str | None,
    parameters: dict[str, Any],
    data_context: dict[str, Any],
) -> str:
    config_id = content_hash_for_configuration(
        config_kind=config_kind,
        strategy_id=strategy_id,
        model_id=model_id,
        symbol=symbol,
        resolution=resolution,
        horizon_label=horizon_label,
        parameters=parameters,
        data_context=data_context,
    )
    created_at_utc = _utc_now()
    connection.execute(
        """
        INSERT INTO configurations (
            id, config_kind, strategy_id, model_id, symbol, resolution, horizon_label,
            parameters_json, data_context_json, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO NOTHING
        """,
        (
            config_id,
            config_kind,
            strategy_id,
            model_id,
            symbol,
            resolution,
            horizon_label,
            json.dumps(parameters, default=str),
            json.dumps(data_context, default=str),
            created_at_utc,
        ),
    )
    return config_id


def insert_evaluation_run(
    connection: sqlite3.Connection,
    *,
    config_id: str,
    run_kind: str,
    out_dir: Path | str,
    metrics: dict[str, Any],
    compare_session_id: str | None = None,
    experiment_id: str | None = None,
) -> str:
    out_dir_str = str(out_dir)
    existing = connection.execute(
        "SELECT id FROM evaluation_runs WHERE out_dir = ? AND run_kind = ?",
        (out_dir_str, run_kind),
    ).fetchone()
    if existing is not None:
        return str(existing["id"])
    run_id = uuid.uuid4().hex
    connection.execute(
        """
        INSERT INTO evaluation_runs (
            id, run_kind, config_id, out_dir, metrics_json, created_at_utc,
            compare_session_id, experiment_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            run_kind,
            config_id,
            out_dir_str,
            json.dumps(metrics, default=str),
            _utc_now(),
            compare_session_id,
            experiment_id,
        ),
    )
    return run_id


def insert_compare_session(
    connection: sqlite3.Connection,
    *,
    csv_path: str,
    bar_count: int | None,
    best_strategy_id: str | None,
    summary: dict[str, Any],
) -> str:
    session_id = summary.get("compare_session_id") or uuid.uuid4().hex
    connection.execute(
        """
        INSERT OR REPLACE INTO compare_sessions (
            id, csv_path, bar_count, best_strategy_id, summary_json, created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            csv_path,
            bar_count,
            best_strategy_id,
            json.dumps(summary, default=str),
            _utc_now(),
        ),
    )
    return session_id


def upsert_experiment(
    connection: sqlite3.Connection,
    *,
    experiment_id: str,
    pipeline_id: str | None,
    title: str | None,
    status: str | None,
    config_path: str | None,
    solution_root: str | None,
    payload: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO experiments (
            experiment_id, pipeline_id, title, status, config_path, solution_root,
            payload_json, updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(experiment_id) DO UPDATE SET
            pipeline_id = excluded.pipeline_id,
            title = excluded.title,
            status = excluded.status,
            config_path = excluded.config_path,
            solution_root = excluded.solution_root,
            payload_json = excluded.payload_json,
            updated_at_utc = excluded.updated_at_utc
        """,
        (
            experiment_id,
            pipeline_id,
            title,
            status,
            config_path,
            solution_root,
            json.dumps(payload, default=str),
            _utc_now(),
        ),
    )
