from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from traderbot.algorithms.registry import normalize_strategy_mode, strategy_ids_for_mode
from lab.store.catalog import fetch_dataset, fetch_market
from lab.store.queries import fetch_experiment


class JobPayloadError(ValueError):
    pass


def parse_run_bound_utc(raw: Any) -> int | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise JobPayloadError("run window times must be ISO-8601 UTC datetimes") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return int(parsed.timestamp())


def apply_run_window_to_prepared(body: dict[str, Any], prepared: dict[str, Any]) -> None:
    start_unix_seconds = parse_run_bound_utc(body.get("run_start_utc"))
    end_unix_seconds = parse_run_bound_utc(body.get("run_end_utc"))
    if start_unix_seconds is not None and end_unix_seconds is not None:
        if start_unix_seconds >= end_unix_seconds:
            raise JobPayloadError("run_start_utc must be before run_end_utc")
    if start_unix_seconds is not None:
        prepared["run_start_unix_seconds"] = start_unix_seconds
    if end_unix_seconds is not None:
        prepared["run_end_unix_seconds"] = end_unix_seconds


def resolve_csv_from_body(connection: sqlite3.Connection, body: dict[str, Any]) -> str:
    dataset_id = body.get("dataset_id")
    if dataset_id:
        row = fetch_dataset(connection, str(dataset_id))
        if row is None:
            raise JobPayloadError(f"dataset not found: {dataset_id}")
        return str(row["repo_path"])
    csv_path = body.get("csv")
    if csv_path:
        return str(csv_path)
    raise JobPayloadError("dataset_id or csv required")


def apply_strategy_mode(
    connection: sqlite3.Connection,
    body: dict[str, Any],
    *,
    strategy_required: bool,
) -> dict[str, Any]:
    try:
        mode = normalize_strategy_mode(body.get("mode"))
    except ValueError as exc:
        raise JobPayloadError(str(exc)) from exc
    prepared = {**body, "mode": mode}
    if strategy_required:
        strategy_id = str(body.get("strategy_id") or "").strip()
        if not strategy_id:
            raise JobPayloadError("strategy_id required")
        if strategy_id not in strategy_ids_for_mode(mode):
            raise JobPayloadError(f"strategy {strategy_id} is not available in {mode} mode")
        prepared["strategy_id"] = strategy_id
    return prepared


def resolve_pipeline_run_body(connection: sqlite3.Connection, body: dict[str, Any]) -> dict[str, Any]:
    from traderbot.pipelines.registry import get_pipeline

    pipeline_id = str(body.get("pipeline_id") or "").strip()
    if not pipeline_id:
        raise JobPayloadError("pipeline_id required")
    try:
        spec = get_pipeline(pipeline_id)
    except KeyError as exc:
        raise JobPayloadError(str(exc)) from exc

    prepared: dict[str, Any] = {"pipeline_id": pipeline_id}
    input_keys = {field.key for field in spec.inputs}
    all_assets = bool(body.get("all_assets", True))
    if "all_assets" in input_keys:
        prepared["all_assets"] = all_assets

    needs_dataset = any(field.key == "dataset" and field.required for field in spec.inputs)
    dataset_requested = bool(body.get("dataset_id") or body.get("csv"))
    if needs_dataset or ("all_assets" in input_keys and not all_assets):
        if not dataset_requested and not needs_dataset:
            raise JobPayloadError("dataset_id required unless all_assets is set")
        if needs_dataset or dataset_requested:
            prepared["csv"] = resolve_csv_from_body(connection, body)
    elif dataset_requested and "dataset" in input_keys:
        prepared["csv"] = resolve_csv_from_body(connection, body)

    for field in spec.inputs:
        if field.kind == "select":
            raw = body.get(field.key)
            if raw is None or raw == "":
                raw = field.default
            chosen = str(raw)
            allowed = {choice.value for choice in field.options}
            if allowed and chosen not in allowed:
                raise JobPayloadError(f"{field.key} must be one of {sorted(allowed)}")
            prepared[field.key] = chosen
        elif field.kind == "number" and field.key != "days":
            raw_number = body.get(field.key)
            if raw_number is None or raw_number == "":
                raw_number = field.default
            try:
                prepared[field.key] = int(raw_number)
            except (TypeError, ValueError) as exc:
                raise JobPayloadError(f"{field.key} must be an integer") from exc

    if spec.days_kw is not None:
        raw_days = body.get("days")
        if raw_days is None or raw_days == "":
            default = next((field.default for field in spec.inputs if field.key == "days"), "30")
            raw_days = default or "30"
        try:
            days = int(raw_days)
        except (TypeError, ValueError) as exc:
            raise JobPayloadError("days must be an integer") from exc
        if days < 1:
            raise JobPayloadError("days must be at least 1")
        prepared["days"] = days
    return prepared


def resolve_config_path_from_body(connection: sqlite3.Connection, body: dict[str, Any]) -> str:
    experiment_id = body.get("experiment_id")
    if experiment_id:
        experiment = fetch_experiment(connection, str(experiment_id))
        if experiment is None:
            raise JobPayloadError(f"experiment not found: {experiment_id}")
        config_path = experiment.get("config_path")
        if not config_path:
            raise JobPayloadError(f"experiment has no config_path: {experiment_id}")
        return str(config_path)
    config_path = body.get("config_path")
    if config_path:
        return str(config_path)
    raise JobPayloadError("experiment_id or config_path required")


def resolve_custom_research_body(connection: sqlite3.Connection, body: dict[str, Any]) -> dict[str, Any]:
    compare_strategies = bool(body.get("compare_strategies"))
    run_forecasts = bool(body.get("run_forecasts"))
    if run_forecasts:
        raise JobPayloadError("run_forecasts is not supported")
    use_all_hourly_files = bool(body.get("use_all_hourly_files"))
    dataset_ids = body.get("dataset_ids")
    export_market_symbol = body.get("export_market_symbol")
    has_single_export = bool(export_market_symbol and str(export_market_symbol).strip())
    if not compare_strategies and not run_forecasts:
        raise JobPayloadError("enable compare_strategies or run_forecasts")
    if not use_all_hourly_files and not has_single_export:
        if not isinstance(dataset_ids, list) or not dataset_ids:
            raise JobPayloadError(
                "dataset_ids required unless export_market_symbol or use_all_hourly_files",
            )

    prepared: dict[str, Any] = {
        "compare_strategies": compare_strategies,
        "run_forecasts": run_forecasts,
        "use_all_hourly_files": use_all_hourly_files,
        "visualize": bool(body.get("visualize", True)),
        "cash": body.get("cash"),
        "fee": body.get("fee"),
        "vectorbt": body.get("vectorbt"),
        "compare_mode": body.get("compare_mode") or "strategies",
        "train_ratio": body.get("train_ratio"),
    }

    raw_export_days = body.get("export_days")
    try:
        export_days = int(raw_export_days if raw_export_days not in (None, "") else 30)
    except (TypeError, ValueError) as exc:
        raise JobPayloadError("export_days must be an integer") from exc
    if export_days < 1:
        raise JobPayloadError("export_days must be at least 1")
    if has_single_export:
        prepared["export_days"] = export_days
        export_body = dict(body)
        export_body["market_symbol"] = str(export_market_symbol).strip()
        if not export_body.get("interval"):
            export_body["interval"] = "60"
        export_body["days"] = export_days
        if not export_body.get("out"):
            export_body["out"] = "data"
        prepared["export_fields"] = resolve_export_argv_fields(connection, export_body)

    dataset_rows: list[dict[str, Any]] = []
    if isinstance(dataset_ids, list) and dataset_ids:
        for dataset_id in dataset_ids:
            row = fetch_dataset(connection, str(dataset_id))
            if row is None:
                raise JobPayloadError(f"dataset not found: {dataset_id}")
            dataset_rows.append(dict(row))
    prepared["dataset_rows"] = dataset_rows

    strategy_ids = body.get("strategy_ids")
    if strategy_ids is not None:
        if not isinstance(strategy_ids, list) or not strategy_ids:
            raise JobPayloadError("strategy_ids must be a non-empty list when provided")
        prepared["strategy_ids"] = [str(item) for item in strategy_ids]

    max_strategies = body.get("max_strategies")
    if max_strategies is not None and max_strategies != "":
        try:
            max_value = int(max_strategies)
        except (TypeError, ValueError) as exc:
            raise JobPayloadError("max_strategies must be an integer") from exc
        if max_value < 1:
            raise JobPayloadError("max_strategies must be at least 1")
        prepared["max_strategies"] = max_value

    if run_forecasts:
        model_ids = body.get("model_ids")
        if not isinstance(model_ids, list) or not model_ids:
            raise JobPayloadError("model_ids required when run_forecasts is true")
        prepared["model_ids"] = [str(item) for item in model_ids]
        for key in ("horizon_bars", "bar_minutes", "train_supervised_row_count", "test_supervised_row_count"):
            raw = body.get(key)
            if raw is not None and raw != "":
                try:
                    prepared[key] = int(raw)
                except (TypeError, ValueError) as exc:
                    raise JobPayloadError(f"{key} must be an integer") from exc

    for key in ("fast", "slow", "signal", "period", "context_bars"):
        if key in body and body[key] not in (None, ""):
            prepared[key] = body[key]
    for key in ("oversold", "overbought", "num_std", "fee"):
        if key in body and body[key] not in (None, ""):
            prepared[key] = body[key]
    if "price_confirm" in body:
        prepared["price_confirm"] = bool(body["price_confirm"])

    apply_run_window_to_prepared(body, prepared)

    return prepared


def resolve_export_argv_fields(connection: sqlite3.Connection, body: dict[str, Any]) -> dict[str, Any]:
    market_symbol = body.get("market_symbol")
    if market_symbol:
        market = fetch_market(connection, str(market_symbol))
        if market is None:
            raise JobPayloadError(f"market not in catalog: {market_symbol}")
        return {
            "src": market["src"],
            "dst": market["dst"],
            "interval": body.get("interval"),
            "days": body.get("days"),
            "out": body.get("out"),
            "crypto_layout": body.get("crypto_layout"),
        }
    return {
        "src": body.get("src"),
        "dst": body.get("dst"),
        "interval": body.get("interval"),
        "days": body.get("days"),
        "out": body.get("out"),
        "crypto_layout": body.get("crypto_layout"),
    }
