from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from traderbot.algorithms.base import Algorithm
from traderbot.backtesting.engine import BacktestResult
from lab.store.canonical import (
    build_strategy_parameters,
    parse_symbol_resolution_from_csv,
)
from lab.store.constants import (
    CONFIG_KIND_MODEL,
    CONFIG_KIND_STRATEGY,
    RUN_KIND_MODEL_FORECAST,
    RUN_KIND_STRATEGY_BACKTEST,
)
from lab.store.database import open_database
from lab.store.record import (
    insert_compare_session,
    insert_evaluation_run,
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


def record_model_forecast(
    *,
    result_dict: dict[str, Any],
    out_dir: Path,
    csv_path: Path | str | None = None,
    train_ratio: float | None = None,
    experiment_id: str | None = None,
    database_path: Path | None = None,
) -> str | None:
    model_id = result_dict.get("model_id")
    horizon_label = result_dict.get("horizon_label")
    horizon_bars = result_dict.get("horizon_bars")
    extra = result_dict.get("extra") or {}
    symbol, resolution = parse_symbol_resolution_from_csv(csv_path or extra.get("dataset"))
    bar_minutes = extra.get("simulation", {}).get("bar_minutes")
    if bar_minutes is None and resolution and str(resolution).isdigit():
        bar_minutes = int(resolution)
    parameters = {
        "horizon_bars": horizon_bars,
        "bar_minutes": bar_minutes,
        "train_ratio": train_ratio or extra.get("train_ratio"),
        "train_supervised_row_count": extra.get("train_supervised_row_count_requested")
        or extra.get("train_supervised_row_count"),
        "num_boost_round": extra.get("num_boost_round"),
        "simulation": extra.get("simulation"),
    }
    data_context = {
        "csv": str(csv_path) if csv_path else extra.get("dataset"),
        "symbol": symbol,
        "resolution": resolution,
        "n_samples": result_dict.get("n_samples"),
    }
    connection = open_database(database_path)

    def write(connection) -> str:
        csv_text = str(csv_path) if csv_path else extra.get("dataset")
        if csv_text:
            upsert_dataset(
                connection,
                repo_path=str(csv_text),
                source="model_forecast",
                symbol=symbol,
                resolution=str(resolution) if resolution else None,
            )
        config_id = upsert_configuration(
            connection,
            config_kind=CONFIG_KIND_MODEL,
            strategy_id=None,
            model_id=str(model_id) if model_id else None,
            symbol=symbol,
            resolution=str(resolution) if resolution else None,
            horizon_label=str(horizon_label) if horizon_label else None,
            parameters=parameters,
            data_context=data_context,
        )
        return insert_evaluation_run(
            connection,
            config_id=config_id,
            run_kind=RUN_KIND_MODEL_FORECAST,
            out_dir=out_dir,
            metrics=result_dict.get("metrics") or {},
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
