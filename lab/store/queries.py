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

_RETURN_PCT_SQL = (
    "COALESCE("
    "CAST(json_extract(r.metrics_json, '$.return_pct') AS REAL), "
    "CAST(json_extract(r.metrics_json, '$.cash_flow.return_pct') AS REAL)"
    ")"
)
_WIN_RATE_SQL = (
    "COALESCE("
    "CAST(json_extract(r.metrics_json, '$.win_rate_pct') AS REAL), "
    "CAST(json_extract(r.metrics_json, '$.vbt_win_rate_pct') AS REAL), "
    "CAST(json_extract(r.metrics_json, '$.vectorbt.win_rate_pct') AS REAL), "
    "CAST(json_extract(r.metrics_json, '$.trade_win_rate') AS REAL) * "
    "(CASE WHEN CAST(json_extract(r.metrics_json, '$.trade_win_rate') AS REAL) <= 1.0 THEN 100.0 ELSE 1.0 END), "
    "CAST(json_extract(r.metrics_json, '$.win_rate') AS REAL) * "
    "(CASE WHEN CAST(json_extract(r.metrics_json, '$.win_rate') AS REAL) <= 1.0 THEN 100.0 ELSE 1.0 END)"
    ")"
)


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
               AVG({_RETURN_PCT_SQL}) AS avg_return,
               AVG({_WIN_RATE_SQL}) AS avg_win_rate
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
            SUM(CASE WHEN {_RETURN_PCT_SQL} IS NOT NULL THEN 1 ELSE 0 END) AS with_return_n,
            AVG({_WIN_RATE_SQL}) AS avg_win_rate
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
        "avg_win_rate": backtest_row["avg_win_rate"],
    }
    top_markets = connection.execute(
        f"""
        SELECT UPPER(c.symbol) AS symbol, COUNT(*) AS n,
               MAX({_RETURN_PCT_SQL}) AS best_return,
               AVG({_RETURN_PCT_SQL}) AS avg_return,
               AVG({_WIN_RATE_SQL}) AS avg_win_rate
        {_STRATEGY_BACKTEST_FROM}
          AND c.symbol IS NOT NULL AND TRIM(c.symbol) != ''
        GROUP BY UPPER(c.symbol)
        ORDER BY avg_return DESC NULLS LAST, best_return DESC NULLS LAST
        LIMIT 8
        """
    ).fetchall()
    top_intervals = connection.execute(
        f"""
        SELECT COALESCE(NULLIF(TRIM(c.horizon_label), ''), c.resolution) AS interval_label,
               COUNT(*) AS n,
               MAX({_RETURN_PCT_SQL}) AS best_return,
               AVG({_RETURN_PCT_SQL}) AS avg_return,
               AVG({_WIN_RATE_SQL}) AS avg_win_rate
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
               AVG({_RETURN_PCT_SQL}) AS avg_return,
               AVG({_WIN_RATE_SQL}) AS avg_win_rate
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


_OPTIMIZER_CONDITION_SQL = (
    "(COALESCE(json_extract(c.data_context_json, '$.optimizer_enabled'), 0) = 1 "
    "OR COALESCE(json_extract(c.data_context_json, '$.use_optimized_strategy_params'), 0) = 1 "
    "OR COALESCE(json_extract(c.data_context_json, '$.apply_sweep_winner'), 0) = 1 "
    "OR COALESCE(json_extract(c.data_context_json, '$.optimized'), 0) = 1 "
    "OR COALESCE(json_extract(r.metrics_json, '$.optimizer_enabled'), 0) = 1 "
    "OR COALESCE(json_extract(r.metrics_json, '$.use_optimized_strategy_params'), 0) = 1 "
    "OR COALESCE(json_extract(r.metrics_json, '$.apply_sweep_winner'), 0) = 1 "
    "OR COALESCE(json_extract(r.metrics_json, '$.optimized'), 0) = 1)"
)

_TRADES_COUNT_SQL = (
    "COALESCE(CAST(json_extract(r.metrics_json, '$.trades') AS INTEGER), "
    "CAST(json_extract(r.metrics_json, '$.cash_flow.trades') AS INTEGER), 0)"
)


def _resolution_match_clause(resolution: str) -> tuple[str, list[Any]]:
    token = resolution.strip()
    alias_map = {
        "1m": "1",
        "5m": "5",
        "15m": "15",
        "30m": "30",
        "1h": "60",
        "2h": "120",
        "4h": "240",
        "1d": "D",
    }
    candidates = {token}
    lower = token.lower()
    if lower in alias_map:
        candidates.add(alias_map[lower])
    for k, v in alias_map.items():
        if lower == v.lower():
            candidates.add(k)
    parts: list[str] = []
    params: list[Any] = []
    for cand in sorted(candidates):
        parts.append("c.resolution = ?")
        params.append(cand)
        parts.append("c.resolution LIKE ? ESCAPE '\\'")
        params.append(f"{_like_literal(cand)}\\_%")
    return "(" + " OR ".join(parts) + ")", params


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


def _build_run_filters(
    *,
    run_kind: str | None = None,
    strategy_id: str | None = None,
    model_id: str | None = None,
    symbol: str | None = None,
    horizon_label: str | None = None,
    resolution: str | None = None,
    outcome: str | None = None,
    optimizer: str | None = None,
    trades: str | None = None,
    date_range: str | None = None,
    query: str | None = None,
) -> tuple[list[str], list[Any]]:
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
    if resolution:
        res_clause, res_params = _resolution_match_clause(resolution)
        clauses.append(res_clause)
        params.extend(res_params)
    if outcome:
        out_lower = outcome.lower()
        if out_lower == "profitable":
            clauses.append(f"{_RETURN_PCT_SQL} > 0")
        elif out_lower == "loss":
            clauses.append(f"{_RETURN_PCT_SQL} < 0")
        elif out_lower == "breakeven":
            clauses.append(f"{_RETURN_PCT_SQL} = 0")
        elif out_lower == "high_return":
            clauses.append(f"{_RETURN_PCT_SQL} >= 5.0")
    if optimizer:
        opt_lower = optimizer.lower()
        if opt_lower in ("optimized", "1", "true"):
            clauses.append(_OPTIMIZER_CONDITION_SQL)
        elif opt_lower in ("default", "unoptimized", "0", "false"):
            clauses.append(f"NOT {_OPTIMIZER_CONDITION_SQL}")
    if trades:
        tr_lower = trades.lower()
        if tr_lower in ("with_trades", "has_trades", "active"):
            clauses.append(f"{_TRADES_COUNT_SQL} > 0")
        elif tr_lower in ("no_trades", "zero", "zero_trades"):
            clauses.append(f"{_TRADES_COUNT_SQL} = 0")
    if date_range:
        dr_lower = date_range.lower()
        if dr_lower in ("24h", "1d"):
            clauses.append("datetime(r.created_at_utc) >= datetime('now', '-1 day')")
        elif dr_lower in ("7d", "1w"):
            clauses.append("datetime(r.created_at_utc) >= datetime('now', '-7 days')")
        elif dr_lower in ("30d", "1m"):
            clauses.append("datetime(r.created_at_utc) >= datetime('now', '-30 days')")
    if query and query.strip():
        like_pat = f"%{_like_literal(query.strip())}%"
        clauses.append(
            """(
                r.id LIKE ? ESCAPE '\\'
                OR r.run_kind LIKE ? ESCAPE '\\'
                OR c.symbol LIKE ? ESCAPE '\\'
                OR c.strategy_id LIKE ? ESCAPE '\\'
                OR c.model_id LIKE ? ESCAPE '\\'
                OR c.parameters_json LIKE ? ESCAPE '\\'
                OR json_extract(c.data_context_json, '$.csv') LIKE ? ESCAPE '\\'
            )"""
        )
        params.extend([like_pat, like_pat, like_pat, like_pat, like_pat, like_pat, like_pat])
    return clauses, params


def count_evaluation_runs(
    connection: sqlite3.Connection,
    *,
    run_kind: str | None = None,
    strategy_id: str | None = None,
    model_id: str | None = None,
    symbol: str | None = None,
    horizon_label: str | None = None,
    resolution: str | None = None,
    outcome: str | None = None,
    optimizer: str | None = None,
    trades: str | None = None,
    date_range: str | None = None,
    query: str | None = None,
) -> int:
    clauses, params = _build_run_filters(
        run_kind=run_kind,
        strategy_id=strategy_id,
        model_id=model_id,
        symbol=symbol,
        horizon_label=horizon_label,
        resolution=resolution,
        outcome=outcome,
        optimizer=optimizer,
        trades=trades,
        date_range=date_range,
        query=query,
    )
    query_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM evaluation_runs r
        JOIN configurations c ON c.id = r.config_id
        WHERE {' AND '.join(clauses)}
    """
    row = connection.execute(query_sql, params).fetchone()
    return int(row["cnt"]) if row else 0


def list_evaluation_runs(
    connection: sqlite3.Connection,
    *,
    run_kind: str | None = None,
    strategy_id: str | None = None,
    model_id: str | None = None,
    symbol: str | None = None,
    horizon_label: str | None = None,
    resolution: str | None = None,
    outcome: str | None = None,
    optimizer: str | None = None,
    trades: str | None = None,
    date_range: str | None = None,
    query: str | None = None,
    sort_by: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> list[RunRow]:
    clauses, params = _build_run_filters(
        run_kind=run_kind,
        strategy_id=strategy_id,
        model_id=model_id,
        symbol=symbol,
        horizon_label=horizon_label,
        resolution=resolution,
        outcome=outcome,
        optimizer=optimizer,
        trades=trades,
        date_range=date_range,
        query=query,
    )
    sort_map = {
        "created_at_desc": "r.created_at_utc DESC",
        "created_at_asc": "r.created_at_utc ASC",
        "return_desc": f"{_RETURN_PCT_SQL} DESC NULLS LAST, r.created_at_utc DESC",
        "return_asc": f"{_RETURN_PCT_SQL} ASC NULLS LAST, r.created_at_utc DESC",
        "win_rate_desc": f"{_WIN_RATE_SQL} DESC NULLS LAST, r.created_at_utc DESC",
        "win_rate_asc": f"{_WIN_RATE_SQL} ASC NULLS LAST, r.created_at_utc DESC",
        "trades_desc": f"{_TRADES_COUNT_SQL} DESC, r.created_at_utc DESC",
        "trades_asc": f"{_TRADES_COUNT_SQL} ASC, r.created_at_utc DESC",
        "equity_desc": (
            "COALESCE(CAST(json_extract(r.metrics_json, '$.final_equity') AS REAL), "
            "CAST(json_extract(r.metrics_json, '$.cash_flow.final_equity') AS REAL), 0) DESC, "
            "r.created_at_utc DESC"
        ),
        "equity_asc": (
            "COALESCE(CAST(json_extract(r.metrics_json, '$.final_equity') AS REAL), "
            "CAST(json_extract(r.metrics_json, '$.cash_flow.final_equity') AS REAL), 0) ASC, "
            "r.created_at_utc DESC"
        ),
    }
    order_clause = sort_map.get(sort_by or "", "r.created_at_utc DESC")
    params.append(limit)
    params.append(max(offset, 0))
    query_sql = f"""
        SELECT r.*, c.strategy_id, c.model_id, c.symbol, c.resolution, c.horizon_label,
               c.parameters_json, c.data_context_json
        FROM evaluation_runs r
        JOIN configurations c ON c.id = r.config_id
        WHERE {' AND '.join(clauses)}
        ORDER BY {order_clause}
        LIMIT ? OFFSET ?
    """
    rows = connection.execute(query_sql, params).fetchall()
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
