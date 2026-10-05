from __future__ import annotations

from pathlib import Path
from typing import Any

from lab.store import (
    default_database_path,
    fetch_best_sweep,
    fetch_dashboard_stats,
    fetch_evaluation_run,
    list_compare_sessions,
    list_configurations,
    list_evaluation_runs,
    list_experiments,
    list_sweep_sessions,
    open_database,
)
from lab.store.queries import fetch_experiment
from lab.store.catalog import (
    CATALOG_SCOPE_DEFAULT_JOBS,
    CATALOG_SCOPE_NOBITEX_ALL,
    backfill_datasets,
    count_market_catalog,
    ensure_default_jobs_catalog,
    fetch_dataset,
    fetch_dataset_by_repo_path,
    list_datasets,
    load_market_catalog_scope,
    market_catalog_updated_at,
    refresh_market_catalog,
    search_market_catalog,
)
from lab.store.database import init_database
from traderbot.markets.market_data import RESOLUTIONS
from lab.artifacts import (
    list_png_artifacts_for_run,
    artifact_relpath_for_out_dir,
    resolve_artifact_path,
    resolve_run_artifact,
)


LAB_API_FEATURES = (
    "market_catalog",
    "datasets",
    "catalog_jobs",
    "pipelines",
    "experiment_sync",
    "live_job_logs",
    "auth_api",
    "terminal_jobs",
    "catalog_api",
    "strategy_sweep",
)


def create_app(database_path: Path | None = None):
    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse
    except ImportError as import_error:
        raise ImportError(
            "Lab API requires optional dependencies. Install: pip install -e '.[ui]'",
        ) from import_error

    app = FastAPI(title="Traderbot Lab API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_connection():
        return open_database(database_path or default_database_path())

    @app.on_event("startup")
    def _lab_startup() -> None:
        from lab.jobs import reconcile_orphan_lab_jobs

        connection = get_connection()
        try:
            init_database(connection)
            ensure_default_jobs_catalog(connection)
            reconcile_orphan_lab_jobs(connection)
            connection.commit()
        finally:
            connection.close()

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "features": list(LAB_API_FEATURES),
        }

    @app.get("/api/stats")
    def api_stats():
        connection = get_connection()
        try:
            return fetch_dashboard_stats(connection)
        finally:
            connection.close()

    @app.get("/api/runs")
    def api_runs(
        run_kind: str | None = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        model_id: str | None = None,
        horizon_label: str | None = None,
        limit: int = Query(default=200, le=500),
    ):
        connection = get_connection()
        try:
            rows = list_evaluation_runs(
                connection,
                run_kind=run_kind,
                symbol=symbol,
                strategy_id=strategy_id,
                model_id=model_id,
                horizon_label=horizon_label,
                limit=limit,
            )
            return [_run_to_api(connection, row) for row in rows]
        finally:
            connection.close()

    @app.get("/api/runs/{run_id}")
    def api_run(run_id: str):
        connection = get_connection()
        try:
            row = fetch_evaluation_run(connection, run_id)
            if row is None:
                raise HTTPException(status_code=404, detail="run not found")
            payload = _run_to_api(connection, row)
            png_paths = list_png_artifacts_for_run(row.out_dir)
            payload["artifacts"] = [
                _artifact_ref(
                    path,
                    f"/api/runs/{run_id}/artifact?file={artifact_relpath_for_out_dir(path, row.out_dir)}",
                )
                for path in png_paths
            ]
            return payload
        finally:
            connection.close()

    @app.get("/api/runs/{run_id}/artifact")
    def api_run_artifact(run_id: str, file: str = Query(..., min_length=1)):
        connection = get_connection()
        try:
            row = fetch_evaluation_run(connection, run_id)
        finally:
            connection.close()
        if row is None:
            raise HTTPException(status_code=404, detail="run not found")
        resolved = resolve_run_artifact(str(row.out_dir), file)
        if resolved is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(resolved, filename=resolved.name)

    @app.get("/api/configurations")
    def api_configurations(config_kind: str | None = None, limit: int = Query(default=200, le=500)):
        connection = get_connection()
        try:
            rows = list_configurations(connection, config_kind=config_kind, limit=limit)
            return [_configuration_to_api(connection, row) for row in rows]
        finally:
            connection.close()

    @app.get("/api/experiments")
    def api_experiments(limit: int = Query(default=100, le=200)):
        from lab.experiment_catalog import sync_experiment_config_files

        connection = get_connection()
        try:
            sync_experiment_config_files(connection)
            rows = list_experiments(connection, limit=limit)
            return [_experiment_to_api(row) for row in rows]
        finally:
            connection.close()

    @app.post("/api/experiments/sync")
    def api_experiments_sync():
        from lab.experiment_catalog import sync_experiment_config_files

        connection = get_connection()
        try:
            registered_count = sync_experiment_config_files(connection)
            return {"registered_count": registered_count}
        finally:
            connection.close()

    @app.get("/api/pipelines")
    def api_pipelines():
        from traderbot.pipelines.registry import list_pipelines, pipeline_spec_to_api

        return [pipeline_spec_to_api(spec) for spec in list_pipelines()]

    @app.get("/api/experiments/{experiment_id}/artifacts")
    def api_experiment_artifacts(experiment_id: str):
        connection = get_connection()
        try:
            experiment = fetch_experiment(connection, experiment_id)
        finally:
            connection.close()
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        solution_root = experiment.get("solution_root")
        if not solution_root:
            return {"artifacts": []}
        paths = list_png_artifacts_for_run(str(solution_root))
        return {
            "artifacts": [
                _artifact_ref(path, f"/api/experiments/{experiment_id}/artifact?file={Path(path).name}")
                for path in paths
            ],
        }

    @app.get("/api/experiments/{experiment_id}/artifact")
    def api_experiment_artifact(experiment_id: str, file: str = Query(..., min_length=1)):
        connection = get_connection()
        try:
            experiment = fetch_experiment(connection, experiment_id)
        finally:
            connection.close()
        if experiment is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        solution_root = experiment.get("solution_root")
        if not solution_root:
            raise HTTPException(status_code=404, detail="artifact not found")
        from pathlib import PurePosixPath

        safe_name = PurePosixPath(file).name
        if safe_name != file:
            raise HTTPException(status_code=400, detail="invalid file name")
        candidate = f"{str(solution_root).rstrip('/')}/{safe_name}"
        resolved = resolve_artifact_path(candidate)
        if resolved is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(resolved, filename=resolved.name)

    @app.get("/api/compare-sessions")
    def api_compare_sessions(limit: int = Query(default=50, le=100)):
        connection = get_connection()
        try:
            rows = list_compare_sessions(connection, limit=limit)
            return [_compare_to_api(connection, row) for row in rows]
        finally:
            connection.close()

    @app.get("/api/sweeps")
    def api_sweeps(
        strategy_id: str | None = Query(default=None),
        symbol: str | None = Query(default=None),
        limit: int = Query(default=50, le=200),
    ):
        connection = get_connection()
        try:
            return list_sweep_sessions(
                connection, strategy_id=strategy_id, symbol=symbol, limit=limit
            )
        finally:
            connection.close()

    @app.get("/api/sweeps/best")
    def api_sweeps_best(
        strategy_id: str = Query(...),
        symbol: str | None = Query(default=None),
        resolution: str | None = Query(default=None),
    ):
        connection = get_connection()
        try:
            row = fetch_best_sweep(
                connection, strategy_id=strategy_id, symbol=symbol, resolution=resolution
            )
        finally:
            connection.close()
        if row is None:
            raise HTTPException(status_code=404, detail="no sweep winner found")
        return row

    @app.get("/api/compare-sessions/{session_id}/artifact")
    def api_compare_session_artifact(session_id: str, path: str = Query(..., min_length=1)):
        connection = get_connection()
        try:
            rows = list_compare_sessions(connection, limit=500)
        finally:
            connection.close()
        if not any(row["id"] == session_id for row in rows):
            raise HTTPException(status_code=404, detail="compare session not found")
        resolved = resolve_artifact_path(path)
        if resolved is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(resolved, filename=resolved.name)

    @app.get("/api/datasets")
    def api_datasets(limit: int = Query(default=200, le=500)):
        connection = get_connection()
        try:
            backfill_datasets(connection)
            connection.commit()
            return list_datasets(connection, limit=limit)
        finally:
            connection.close()

    @app.get("/api/datasets/{dataset_id}/download")
    def api_dataset_download(dataset_id: str):
        connection = get_connection()
        try:
            row = fetch_dataset(connection, dataset_id)
        finally:
            connection.close()
        if row is None:
            raise HTTPException(status_code=404, detail="dataset not found")
        resolved = resolve_artifact_path(str(row["repo_path"]))
        if resolved is None:
            raise HTTPException(status_code=404, detail="dataset file not found on disk")
        return FileResponse(resolved, filename=resolved.name)

    @app.get("/api/data/csv-files")
    def api_data_csv_files(limit: int = Query(default=200, le=500)):
        connection = get_connection()
        try:
            backfill_datasets(connection)
            connection.commit()
            return list_datasets(connection, limit=limit)
        finally:
            connection.close()

    @app.get("/api/data/markets")
    def api_data_markets(
        scope: str = Query(
            default=CATALOG_SCOPE_NOBITEX_ALL,
            description=f"{CATALOG_SCOPE_DEFAULT_JOBS} or {CATALOG_SCOPE_NOBITEX_ALL}",
        ),
        q: str | None = Query(default=None, description="Server-side search (optional; UI uses local filter)"),
        limit: int = Query(default=100, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
        catalog: bool = Query(
            default=False,
            description="If true, return the full cloned scope from SQLite (for client-side search)",
        ),
    ):
        if scope not in (CATALOG_SCOPE_DEFAULT_JOBS, CATALOG_SCOPE_NOBITEX_ALL):
            raise HTTPException(status_code=400, detail="unsupported market catalog scope")
        connection = get_connection()
        try:
            if scope == CATALOG_SCOPE_DEFAULT_JOBS:
                ensure_default_jobs_catalog(connection)
                connection.commit()
            if catalog:
                markets = load_market_catalog_scope(connection, catalog_scope=scope)
                matched_count = len(markets)
            else:
                markets, matched_count = search_market_catalog(
                    connection,
                    catalog_scope=scope,
                    query=q,
                    limit=limit,
                    offset=offset,
                )
            total_in_catalog = count_market_catalog(connection, catalog_scope=scope)
            updated_at_utc = market_catalog_updated_at(connection, catalog_scope=scope)
        finally:
            connection.close()
        return {
            "catalog_scope": scope,
            "total_in_catalog": total_in_catalog,
            "matched_count": matched_count,
            "offset": 0 if catalog else offset,
            "limit": len(markets) if catalog else limit,
            "updated_at_utc": updated_at_utc,
            "markets": [
                {
                    "symbol": market["symbol"],
                    "src": market["src"],
                    "dst": market["dst"],
                    "label": market["label"],
                }
                for market in markets
            ],
            "udf_resolutions": list(RESOLUTIONS),
        }

    @app.post("/api/data/markets/sync")
    def api_sync_market_catalog(
        scope: str = Query(
            default=CATALOG_SCOPE_NOBITEX_ALL,
            description=f"Re-clone from Nobitex or jobs file into SQLite ({CATALOG_SCOPE_NOBITEX_ALL} hits /market/stats)",
        ),
    ):
        if scope not in (CATALOG_SCOPE_DEFAULT_JOBS, CATALOG_SCOPE_NOBITEX_ALL):
            raise HTTPException(status_code=400, detail="unsupported market catalog scope")
        connection = get_connection()
        try:
            cloned_count = refresh_market_catalog(connection, catalog_scope=scope)
            connection.commit()
            updated_at_utc = market_catalog_updated_at(connection, catalog_scope=scope)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Could not clone market catalog from Nobitex: {exc}",
            ) from exc
        finally:
            connection.close()
        return {
            "catalog_scope": scope,
            "cloned_count": cloned_count,
            "updated_at_utc": updated_at_utc,
        }

    @app.get("/api/artifacts/list")
    def api_list_artifacts(out_dir: str = Query(..., description="Run or solution output directory")):
        return {"paths": list_png_artifacts_for_run(out_dir)}

    @app.get("/artifact")
    def artifact(path: str = Query(..., description="Repo-relative file path")):
        resolved = resolve_artifact_path(path)
        if resolved is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return FileResponse(resolved, filename=resolved.name)

    from lab.auth_routes import register_auth_routes
    from lab.catalog_routes import register_catalog_routes
    from lab.jobs import register_job_routes

    register_catalog_routes(app)
    register_auth_routes(app, get_connection)
    register_job_routes(app, get_connection)

    return app


def _artifact_file_name(relative_path: str, out_dir: str) -> str:
    from pathlib import PurePosixPath

    out_prefix = str(out_dir).rstrip("/") + "/"
    if relative_path.startswith(out_prefix):
        return relative_path[len(out_prefix) :]
    return PurePosixPath(relative_path).name


def _artifact_ref(relative_path: str, api_path: str) -> dict[str, str]:
    from pathlib import PurePosixPath

    return {
        "name": PurePosixPath(relative_path).name,
        "url": api_path,
    }


def _sanitize_data_context(data_context: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(data_context)
    cleaned.pop("csv", None)
    return cleaned


def _dataset_fields_for_csv(connection, csv_path: str | None) -> dict[str, Any]:
    if not csv_path:
        return {"dataset_id": None, "dataset_label": None}
    row = fetch_dataset_by_repo_path(connection, str(csv_path))
    if row is None:
        return {"dataset_id": None, "dataset_label": None}
    return {"dataset_id": row["id"], "dataset_label": row["label"]}


def _run_to_api(connection, row) -> dict[str, Any]:
    dataset_fields = _dataset_fields_for_csv(connection, row.data_context.get("csv"))
    return {
        "id": row.id,
        "run_kind": row.run_kind,
        "config_id": row.config_id,
        "strategy_id": row.strategy_id,
        "model_id": row.model_id,
        "symbol": row.symbol,
        "resolution": row.resolution,
        "horizon_label": row.horizon_label,
        "parameters": row.parameters,
        "data_context": _sanitize_data_context(row.data_context),
        "metrics": row.metrics,
        "created_at_utc": row.created_at_utc,
        "compare_session_id": row.compare_session_id,
        "experiment_id": row.experiment_id,
        "results_download_url": f"/api/runs/{row.id}/artifact?file=results.json",
        **dataset_fields,
    }


def _configuration_to_api(connection, row: dict[str, Any]) -> dict[str, Any]:
    dataset_fields = _dataset_fields_for_csv(connection, row.get("data_context", {}).get("csv"))
    return {
        "id": row["id"],
        "config_kind": row["config_kind"],
        "strategy_id": row["strategy_id"],
        "model_id": row["model_id"],
        "symbol": row["symbol"],
        "resolution": row["resolution"],
        "horizon_label": row["horizon_label"],
        "parameters": row["parameters"],
        "data_context": _sanitize_data_context(row.get("data_context") or {}),
        "created_at_utc": row["created_at_utc"],
        **dataset_fields,
    }


def _experiment_to_api(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") or {}
    test_steps = payload.get("test_steps")
    step_count = len(test_steps) if isinstance(test_steps, list) else 0
    last_error = payload.get("last_error")
    return {
        "experiment_id": row["experiment_id"],
        "pipeline_id": row["pipeline_id"],
        "title": row["title"],
        "status": row["status"],
        "payload": payload,
        "updated_at_utc": row["updated_at_utc"],
        "runnable": bool(row.get("config_path")),
        "test_step_count": step_count,
        "last_error": last_error if last_error else None,
    }


def _compare_to_api(connection, row: dict[str, Any]) -> dict[str, Any]:
    from urllib.parse import quote

    dataset_fields = _dataset_fields_for_csv(connection, row.get("csv_path"))
    session_id = row["id"]
    summary = row.get("summary") or {}
    visualization = summary.get("visualization")
    artifact_rows: list[dict[str, str]] = []
    if isinstance(visualization, dict):
        for path in visualization.values():
            if not path:
                continue
            path_text = str(path)
            artifact_rows.append(
                _artifact_ref(
                    path_text,
                    f"/api/compare-sessions/{session_id}/artifact?path={quote(path_text, safe='')}",
                ),
            )
    return {
        "id": session_id,
        "bar_count": row["bar_count"],
        "best_strategy_id": row["best_strategy_id"],
        "summary": summary,
        "created_at_utc": row["created_at_utc"],
        "artifacts": artifact_rows,
        **dataset_fields,
    }
