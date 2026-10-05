from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RunRow:
    id: str
    run_kind: str
    config_id: str
    strategy_id: str | None
    model_id: str | None
    symbol: str | None
    resolution: str | None
    horizon_label: str | None
    parameters: dict[str, Any]
    data_context: dict[str, Any]
    out_dir: str
    metrics: dict[str, Any]
    created_at_utc: str
    compare_session_id: str | None
    experiment_id: str | None


def _row_to_run(row: sqlite3.Row) -> RunRow:
    return RunRow(
        id=row["id"],
        run_kind=row["run_kind"],
        config_id=row["config_id"],
        strategy_id=row["strategy_id"],
        model_id=row["model_id"],
        symbol=row["symbol"],
        resolution=row["resolution"],
        horizon_label=row["horizon_label"],
        parameters=json.loads(row["parameters_json"]),
        data_context=json.loads(row["data_context_json"]),
        out_dir=row["out_dir"],
        metrics=json.loads(row["metrics_json"]),
        created_at_utc=row["created_at_utc"],
        compare_session_id=row["compare_session_id"],
        experiment_id=row["experiment_id"],
    )


def fetch_dashboard_stats(connection: sqlite3.Connection) -> dict[str, Any]:
    run_count = connection.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone()[0]
    config_count = connection.execute("SELECT COUNT(*) FROM configurations").fetchone()[0]
    compare_count = connection.execute("SELECT COUNT(*) FROM compare_sessions").fetchone()[0]
    experiment_count = connection.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    top_strategies = connection.execute(
        """
        SELECT c.strategy_id, COUNT(*) AS n,
               MAX(CAST(json_extract(r.metrics_json, '$.return_pct') AS REAL)) AS best_return
        FROM evaluation_runs r
        JOIN configurations c ON c.id = r.config_id
        WHERE r.run_kind = 'strategy_backtest' AND c.strategy_id IS NOT NULL
        GROUP BY c.strategy_id
        ORDER BY best_return DESC NULLS LAST
        LIMIT 8
        """
    ).fetchall()
    top_models = connection.execute(
        """
        SELECT c.model_id, c.horizon_label, COUNT(*) AS n,
               MAX(CAST(json_extract(r.metrics_json, '$.directional_accuracy') AS REAL)) AS best_dir
        FROM evaluation_runs r
        JOIN configurations c ON c.id = r.config_id
        WHERE r.run_kind = 'model_forecast' AND c.model_id IS NOT NULL
        GROUP BY c.model_id, c.horizon_label
        ORDER BY best_dir DESC NULLS LAST
        LIMIT 8
        """
    ).fetchall()
    return {
        "run_count": run_count,
        "config_count": config_count,
        "compare_count": compare_count,
        "experiment_count": experiment_count,
        "top_strategies": [dict(row) for row in top_strategies],
        "top_models": [dict(row) for row in top_models],
    }


def list_evaluation_runs(
    connection: sqlite3.Connection,
    *,
    run_kind: str | None = None,
    strategy_id: str | None = None,
    model_id: str | None = None,
    symbol: str | None = None,
    horizon_label: str | None = None,
    limit: int = 200,
) -> list[RunRow]:
    clauses = ["1=1"]
    params: list[Any] = []
    if run_kind:
        clauses.append("r.run_kind = ?")
        params.append(run_kind)
    if strategy_id:
        clauses.append("c.strategy_id = ?")
        params.append(strategy_id)
    if model_id:
        clauses.append("c.model_id = ?")
        params.append(model_id)
    if symbol:
        clauses.append("c.symbol = ?")
        params.append(symbol.upper())
    if horizon_label:
        clauses.append("c.horizon_label = ?")
        params.append(horizon_label)
    params.append(limit)
    query = f"""
        SELECT r.*, c.strategy_id, c.model_id, c.symbol, c.resolution, c.horizon_label,
               c.parameters_json, c.data_context_json
        FROM evaluation_runs r
        JOIN configurations c ON c.id = r.config_id
        WHERE {' AND '.join(clauses)}
        ORDER BY r.created_at_utc DESC
        LIMIT ?
    """
    rows = connection.execute(query, params).fetchall()
    return [_row_to_run(row) for row in rows]


def fetch_evaluation_run(connection: sqlite3.Connection, run_id: str) -> RunRow | None:
    row = connection.execute(
        """
        SELECT r.*, c.strategy_id, c.model_id, c.symbol, c.resolution, c.horizon_label,
               c.parameters_json, c.data_context_json
        FROM evaluation_runs r
        JOIN configurations c ON c.id = r.config_id
        WHERE r.id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    return _row_to_run(row)


def list_configurations(
    connection: sqlite3.Connection,
    *,
    config_kind: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    if config_kind:
        rows = connection.execute(
            """
            SELECT * FROM configurations
            WHERE config_kind = ?
            ORDER BY created_at_utc DESC
            LIMIT ?
            """,
            (config_kind, limit),
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT * FROM configurations ORDER BY created_at_utc DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "id": row["id"],
                "config_kind": row["config_kind"],
                "strategy_id": row["strategy_id"],
                "model_id": row["model_id"],
                "symbol": row["symbol"],
                "resolution": row["resolution"],
                "horizon_label": row["horizon_label"],
                "parameters": json.loads(row["parameters_json"]),
                "data_context": json.loads(row["data_context_json"]),
                "created_at_utc": row["created_at_utc"],
            }
        )
    return out


def list_experiments(connection: sqlite3.Connection, limit: int = 100) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM experiments ORDER BY updated_at_utc DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        {
            "experiment_id": row["experiment_id"],
            "pipeline_id": row["pipeline_id"],
            "title": row["title"],
            "status": row["status"],
            "config_path": row["config_path"],
            "solution_root": row["solution_root"],
            "payload": json.loads(row["payload_json"]),
            "updated_at_utc": row["updated_at_utc"],
        }
        for row in rows
    ]


def fetch_experiment(connection: sqlite3.Connection, experiment_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM experiments WHERE experiment_id = ?",
        (experiment_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "experiment_id": row["experiment_id"],
        "pipeline_id": row["pipeline_id"],
        "title": row["title"],
        "status": row["status"],
        "config_path": row["config_path"],
        "solution_root": row["solution_root"],
        "payload": json.loads(row["payload_json"]),
        "updated_at_utc": row["updated_at_utc"],
    }


def list_compare_sessions(connection: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM compare_sessions ORDER BY created_at_utc DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [
        _compare_session_to_api(row)
        for row in rows
    ]


def _compare_session_to_api(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "csv_path": row["csv_path"],
        "bar_count": row["bar_count"],
        "best_strategy_id": row["best_strategy_id"],
        "summary": json.loads(row["summary_json"]),
        "created_at_utc": row["created_at_utc"],
    }
