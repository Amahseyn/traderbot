from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from traderbot.markets.market_data import RESOLUTIONS
from traderbot.utils.horizons import resolution_tokens_for_horizon_label


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


_STRATEGY_BACKTEST_FROM = """
    FROM evaluation_runs r
    JOIN configurations c ON c.id = r.config_id
    WHERE r.run_kind = 'strategy_backtest'
"""

_RETURN_PCT_SQL = "CAST(json_extract(r.metrics_json, '$.return_pct') AS REAL)"


def fetch_dashboard_stats(connection: sqlite3.Connection) -> dict[str, Any]:
    run_count = connection.execute("SELECT COUNT(*) FROM evaluation_runs").fetchone()[0]
    config_count = connection.execute("SELECT COUNT(*) FROM configurations").fetchone()[0]
    compare_count = connection.execute("SELECT COUNT(*) FROM compare_sessions").fetchone()[0]
    sweep_count = connection.execute("SELECT COUNT(*) FROM sweep_sessions").fetchone()[0]
    experiment_count = connection.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    top_strategies = connection.execute(
        f"""
        SELECT c.strategy_id, COUNT(*) AS n,
               MAX({_RETURN_PCT_SQL}) AS best_return,
               AVG({_RETURN_PCT_SQL}) AS avg_return
        {_STRATEGY_BACKTEST_FROM}
          AND c.strategy_id IS NOT NULL
        GROUP BY c.strategy_id
        ORDER BY best_return DESC NULLS LAST
        LIMIT 8
        """
    ).fetchall()
    backtest_row = connection.execute(
        f"""
        SELECT
            COUNT(*) AS n,
            AVG({_RETURN_PCT_SQL}) AS avg_return,
            MAX({_RETURN_PCT_SQL}) AS best_return,
            MIN({_RETURN_PCT_SQL}) AS worst_return,
            SUM(CASE WHEN {_RETURN_PCT_SQL} > 0 THEN 1 ELSE 0 END) AS positive_n,
            SUM(CASE WHEN {_RETURN_PCT_SQL} IS NOT NULL THEN 1 ELSE 0 END) AS with_return_n
        {_STRATEGY_BACKTEST_FROM}
        """
    ).fetchone()
    with_return_n = int(backtest_row["with_return_n"] or 0)
    positive_n = int(backtest_row["positive_n"] or 0)
    backtest_summary = {
        "count": int(backtest_row["n"] or 0),
        "avg_return": backtest_row["avg_return"],
        "best_return": backtest_row["best_return"],
        "worst_return": backtest_row["worst_return"],
        "positive_pct": positive_n / with_return_n * 100 if with_return_n else None,
    }
    top_markets = connection.execute(
        f"""
        SELECT c.symbol, COUNT(*) AS n,
               MAX({_RETURN_PCT_SQL}) AS best_return,
               AVG({_RETURN_PCT_SQL}) AS avg_return
        {_STRATEGY_BACKTEST_FROM}
          AND c.symbol IS NOT NULL AND TRIM(c.symbol) != ''
        GROUP BY c.symbol
        ORDER BY avg_return DESC NULLS LAST, best_return DESC NULLS LAST
        LIMIT 8
        """
    ).fetchall()
    top_intervals = connection.execute(
        f"""
        SELECT COALESCE(NULLIF(TRIM(c.horizon_label), ''), c.resolution) AS interval_label,
               COUNT(*) AS n,
               MAX({_RETURN_PCT_SQL}) AS best_return,
               AVG({_RETURN_PCT_SQL}) AS avg_return
        {_STRATEGY_BACKTEST_FROM}
          AND COALESCE(NULLIF(TRIM(c.horizon_label), ''), c.resolution) IS NOT NULL
        GROUP BY interval_label
        ORDER BY avg_return DESC NULLS LAST, best_return DESC NULLS LAST
        LIMIT 8
        """
    ).fetchall()
    strategy_catalog_stats = connection.execute(
        f"""
        SELECT c.strategy_id, COUNT(*) AS n,
               MAX({_RETURN_PCT_SQL}) AS best_return,
               AVG({_RETURN_PCT_SQL}) AS avg_return
        {_STRATEGY_BACKTEST_FROM}
          AND c.strategy_id IS NOT NULL
        GROUP BY c.strategy_id
        ORDER BY best_return DESC NULLS LAST
        """
    ).fetchall()
    return {
        "run_count": run_count,
        "config_count": config_count,
        "compare_count": compare_count,
        "sweep_count": sweep_count,
        "experiment_count": experiment_count,
        "backtest_summary": backtest_summary,
        "top_strategies": [dict(row) for row in top_strategies],
        "strategy_catalog_stats": [dict(row) for row in strategy_catalog_stats],
        "top_markets": [dict(row) for row in top_markets],
        "top_intervals": [dict(row) for row in top_intervals],
    }


def _like_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _horizon_match_clause(label: str) -> tuple[str, list[Any]]:
    """Match a horizon on the configuration, its dataset folder, or bar size.

    Strategy runs store the candle token on ``resolution`` (``60``, ``60_last24h``)
    and leave ``horizon_label`` empty. ``1h`` still means those 60-minute runs.
    """
    parts = [
        "c.horizon_label = ?",
        """EXISTS (
            SELECT 1 FROM datasets d
            WHERE d.repo_path = json_extract(c.data_context_json, '$.csv')
              AND d.horizon_label = ?
        )""",
        "json_extract(c.data_context_json, '$.csv') LIKE ? ESCAPE '\\'",
    ]
    params: list[Any] = [
        label,
        label,
        f"%/horizons/{_like_literal(label)}/%",
    ]
    for token in resolution_tokens_for_horizon_label(label, RESOLUTIONS):
        parts.append("c.resolution = ?")
        params.append(token)
        parts.append("c.resolution LIKE ? ESCAPE '\\'")
        params.append(f"{_like_literal(token)}\\_%")
    return "(" + " OR ".join(parts) + ")", params


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
        clause, horizon_params = _horizon_match_clause(horizon_label)
        clauses.append(clause)
        params.extend(horizon_params)
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


def _sweep_session_to_api(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "strategy_id": row["strategy_id"],
        "symbol": row["symbol"],
        "resolution": row["resolution"],
        "horizon_label": row["horizon_label"],
        "csv_path": row["csv_path"],
        "bar_count": row["bar_count"],
        "rank_by": row["rank_by"],
        "holdout_tail_bars": row["holdout_tail_bars"],
        "min_trades": row["min_trades"],
        "cash": row["cash"],
        "fee": row["fee"],
        "param_grid": json.loads(row["param_grid_json"]),
        "best_params": json.loads(row["best_params_json"]),
        "best_metrics": json.loads(row["best_metrics_json"]),
        "config_id": row["config_id"],
        "manifest_path": row["manifest_path"],
        "optimize_start_utc": row["optimize_start_utc"],
        "optimize_end_utc": row["optimize_end_utc"],
        "compare_start_utc": row["compare_start_utc"],
        "compare_end_utc": row["compare_end_utc"],
        "created_at_utc": row["created_at_utc"],
    }


def list_sweep_sessions(
    connection: sqlite3.Connection,
    *,
    strategy_id: str | None = None,
    symbol: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    clauses = ["1=1"]
    params: list[Any] = []
    if strategy_id:
        clauses.append("strategy_id = ?")
        params.append(strategy_id)
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol.upper())
    params.append(limit)
    rows = connection.execute(
        f"SELECT * FROM sweep_sessions WHERE {' AND '.join(clauses)}"
        " ORDER BY created_at_utc DESC LIMIT ?",
        params,
    ).fetchall()
    return [_sweep_session_to_api(row) for row in rows]


def _horizon_filter_tiers(horizon_label: str | None) -> list[tuple[str | None, list[Any]]]:
    """Horizon filters in lookup order: exact label, then unlabeled rows, then any row."""
    tiers: list[tuple[str | None, list[Any]]] = []
    label = str(horizon_label or "").strip()
    if label:
        tiers.append(("horizon_label = ?", [label]))
    tiers.append(("(horizon_label IS NULL OR horizon_label = '')", []))
    tiers.append((None, []))
    return tiers


def fetch_best_sweep(
    connection: sqlite3.Connection,
    *,
    strategy_id: str,
    symbol: str | None = None,
    resolution: str | None = None,
    horizon_label: str | None = None,
) -> dict[str, Any] | None:
    for horizon_clause, horizon_params in _horizon_filter_tiers(horizon_label):
        clauses = ["strategy_id = ?"]
        params: list[Any] = [strategy_id]
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol.upper())
        if resolution:
            clauses.append("resolution = ?")
            params.append(resolution)
        if horizon_clause is not None:
            clauses.append(horizon_clause)
            params.extend(horizon_params)
        row = connection.execute(
            f"SELECT * FROM sweep_sessions WHERE {' AND '.join(clauses)}"
            " ORDER BY created_at_utc DESC LIMIT 1",
            params,
        ).fetchone()
        if row is not None:
            return _sweep_session_to_api(row)
    return None
