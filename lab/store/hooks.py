from __future__ import annotations

from pathlib import Path
from typing import Any

from traderbot.algorithms.base import Algorithm
from traderbot.backtesting.engine import BacktestResult
from lab.store.canonical import (
    build_strategy_parameters,
    parse_symbol_resolution_from_csv,
)
from lab.store.constants import (
    CONFIG_KIND_STRATEGY,
    CONFIG_KIND_SWEEP_BEST,
    RUN_KIND_STRATEGY_BACKTEST,
)
from lab.store.database import open_database
from lab.store.record import (
    insert_compare_session,
    insert_evaluation_run,
    insert_sweep_session,
    upsert_configuration,
    upsert_experiment,
)
from lab.store.catalog import upsert_dataset


def _commit_record(connection, callback):
    try:
        result = callback(connection)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise


def record_strategy_backtest(
    algorithm: Algorithm,
    backtest_result: BacktestResult,
    *,
    out_dir: Path,
    bars: int,
    summary: dict[str, Any],
    extra: dict[str, Any] | None = None,
    compare_session_id: str | None = None,
    experiment_id: str | None = None,
    database_path: Path | None = None,
) -> str | None:
    extra = dict(extra or {})
    strategy_id = extra.get("strategy_id") or getattr(algorithm, "name", None)
    csv_path = extra.get("csv")
    symbol, resolution = parse_symbol_resolution_from_csv(csv_path)
    parameters = build_strategy_parameters(algorithm)
    data_context = {
        "csv": csv_path,
        "bars": bars,
        "symbol": symbol,
        "resolution": resolution,
    }
    connection = open_database(database_path)

    def write(connection) -> str:
        if csv_path:
            upsert_dataset(
                connection,
                repo_path=str(csv_path),
                source="strategy_backtest",
                symbol=symbol,
                resolution=resolution,
            )
        config_id = upsert_configuration(
            connection,
            config_kind=CONFIG_KIND_STRATEGY,
            strategy_id=str(strategy_id) if strategy_id else None,
            model_id=None,
            symbol=symbol,
            resolution=resolution,
            horizon_label=None,
            parameters=parameters,
            data_context=data_context,
        )
        return insert_evaluation_run(
            connection,
            config_id=config_id,
            run_kind=RUN_KIND_STRATEGY_BACKTEST,
            out_dir=out_dir,
            metrics=summary,
            compare_session_id=compare_session_id,
            experiment_id=experiment_id,
        )

    try:
        return _commit_record(connection, write)
    finally:
        connection.close()


def record_compare_session(
    *,
    compare_payload: dict[str, Any],
    database_path: Path | None = None,
) -> str | None:
    connection = open_database(database_path)

    def write(connection) -> str:
        csv_text = str(compare_payload.get("csv", ""))
        if csv_text:
            upsert_dataset(connection, repo_path=csv_text, source="compare_session")
        return insert_compare_session(
            connection,
            csv_path=str(compare_payload.get("csv", "")),
            bar_count=compare_payload.get("bars"),
            best_strategy_id=compare_payload.get("best_strategy_id"),
            summary=compare_payload,
        )

    try:
        return _commit_record(connection, write)
    finally:
        connection.close()


def record_sweep_session(
    *,
    sweep_payload: dict[str, Any],
    manifest_path: Path | str | None = None,
    database_path: Path | None = None,
) -> str | None:
    best = sweep_payload.get("best") or {}
    best_params = dict(sweep_payload.get("best_params") or {})
    connection = open_database(database_path)

    def write(connection) -> str:
        csv_text = str(sweep_payload.get("csv", ""))
        strategy_id = str(sweep_payload.get("strategy_id", ""))
        symbol, resolution = parse_symbol_resolution_from_csv(csv_text)
        if csv_text:
            upsert_dataset(
                connection,
                repo_path=csv_text,
                source="sweep_session",
                symbol=symbol,
                resolution=resolution,
            )
        config_id = upsert_configuration(
            connection,
            config_kind=CONFIG_KIND_SWEEP_BEST,
            strategy_id=strategy_id or None,
            model_id=None,
            symbol=symbol,
            resolution=resolution,
            horizon_label=None,
            parameters={"strategy_id": strategy_id, **best_params},
            data_context={
                "csv": csv_text,
                "bars": sweep_payload.get("bars"),
                "rank_by": sweep_payload.get("rank_by"),
                "holdout_tail_bars": sweep_payload.get("holdout_tail_bars"),
            },
        )
        return insert_sweep_session(
            connection,
            strategy_id=strategy_id,
            symbol=symbol,
            resolution=resolution,
            horizon_label=None,
            csv_path=csv_text,
            bar_count=sweep_payload.get("bars"),
            rank_by=str(sweep_payload.get("rank_by", "")),
            holdout_tail_bars=sweep_payload.get("holdout_tail_bars"),
            min_trades=sweep_payload.get("min_trades"),
            cash=sweep_payload.get("cash"),
            fee=sweep_payload.get("fee"),
            param_grid={k: list(v) for k, v in dict(sweep_payload.get("param_grid", {}) or {}).items()},
            best_params=best_params,
            best_metrics={
                key: best.get(key)
                for key in ("return_pct", "holdout_return_pct", "trades", "final_equity")
            },
            config_id=config_id,
            manifest_path=str(manifest_path) if manifest_path else None,
        )

    try:
        return _commit_record(connection, write)
    finally:
        connection.close()


def record_experiment_snapshot(
    *,
    experiment_id: str,
    pipeline_id: str | None,
    title: str | None,
    status: str | None,
    config_path: str | None,
    solution_root: str | None,
    payload: dict[str, Any],
    database_path: Path | None = None,
) -> None:
    connection = open_database(database_path)

    def write(connection) -> None:
        upsert_experiment(
            connection,
            experiment_id=experiment_id,
            pipeline_id=pipeline_id,
            title=title,
            status=status,
            config_path=config_path,
            solution_root=solution_root,
            payload=payload,
        )

    try:
        _commit_record(connection, write)
    finally:
        connection.close()
