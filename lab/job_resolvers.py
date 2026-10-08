from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timezone
from typing import Any

from traderbot.algorithms.registry import normalize_strategy_mode, strategy_ids_for_mode
from traderbot.utils.resolution import resolution_minutes
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


def resolve_sweep_body(connection: sqlite3.Connection, body: dict[str, Any]) -> dict[str, Any]:
    """Validate a strategy-sweep job body (grid optimizer over 1-2 params)."""
    from traderbot.algorithms.cli_args import default_strategy_namespace
    from traderbot.backtesting.sweep import MAX_SWEEP_PARAMS, parse_sweep_param

    prepared = apply_strategy_mode(connection, body, strategy_required=True)
    csv_path = resolve_csv_from_body(connection, body)
    allowed_params = set(vars(default_strategy_namespace()))

    param_grid: dict[str, list[Any]] = {}
    raw_params = body.get("params")
    if isinstance(raw_params, dict):
        for name, raw_values in raw_params.items():
            param_name = str(name).strip()
            if param_name not in allowed_params:
                raise JobPayloadError(f"unknown sweep param {param_name!r}")
            if param_name in param_grid:
                raise JobPayloadError(f"duplicate sweep param {param_name!r}")
            param_grid[param_name] = _coerce_sweep_values(param_name, raw_values)
    raw_specs = body.get("param_specs")
    if raw_specs is None and body.get("param") is not None:
        raw_specs = body.get("param")
    if isinstance(raw_specs, str):
        raw_specs = [raw_specs]
    if raw_specs is not None:
        if not isinstance(raw_specs, list) or not raw_specs:
            raise JobPayloadError("param_specs must be a non-empty list of name=v1,v2 strings")
        for spec in raw_specs:
            try:
                param_name, values = parse_sweep_param(str(spec))
            except ValueError as exc:
                raise JobPayloadError(str(exc)) from exc
            if param_name in param_grid:
                raise JobPayloadError(f"duplicate sweep param {param_name!r}")
            param_grid[param_name] = list(values)
    if not param_grid:
        raise JobPayloadError("sweep requires params {name: [values]} or param_specs [name=v1,v2]")
    if len(param_grid) > MAX_SWEEP_PARAMS:
        raise JobPayloadError(f"sweep requires 1-{MAX_SWEEP_PARAMS} params")

    prepared["csv"] = csv_path
    prepared["param_grid"] = param_grid
    prepared["cash"] = _to_job_float(body.get("cash"), default=10_000.0, field="cash", minimum=0.0)
    prepared["fee"] = _to_job_float(body.get("fee"), default=0.0, field="fee", minimum=0.0)
    holdout_raw = body.get("holdout_tail_bars")
    if holdout_raw in (None, ""):
        prepared["holdout_tail_bars"] = None
    else:
        try:
            holdout_tail_bars = int(holdout_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError) as exc:
            raise JobPayloadError("holdout_tail_bars must be an integer") from exc
        if holdout_tail_bars < 1:
            raise JobPayloadError("holdout_tail_bars must be at least 1")
        prepared["holdout_tail_bars"] = holdout_tail_bars
    try:
        min_trades = int(body.get("min_trades") if body.get("min_trades") not in (None, "") else 0)
        max_combos = int(body.get("max_combos") if body.get("max_combos") not in (None, "") else 64)
    except (TypeError, ValueError) as exc:
        raise JobPayloadError("min_trades and max_combos must be integers") from exc
    if min_trades < 0:
        raise JobPayloadError("min_trades must be at least 0")
    if max_combos < 1:
        raise JobPayloadError("max_combos must be at least 1")
    prepared["min_trades"] = min_trades
    prepared["max_combos"] = max_combos
    for key in allowed_params:
        if key in body and body[key] not in (None, ""):
            prepared[key] = body[key]
    if body.get("out") not in (None, ""):
        prepared["out"] = str(body.get("out"))
    return prepared


def _coerce_sweep_scalar(text: str) -> Any:
    cleaned = text.strip()
    lowered = cleaned.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(cleaned)
    except ValueError:
        pass
    try:
        return float(cleaned)
    except ValueError:
        pass
    return cleaned


def _coerce_sweep_values(param_name: str, raw_values: Any) -> list[Any]:
    if isinstance(raw_values, str):
        items: list[Any] = raw_values.split(",")
    elif isinstance(raw_values, list):
        items = list(raw_values)
    else:
        raise JobPayloadError(f"sweep param {param_name!r} must be a list or comma-separated string")
    values: list[Any] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, str):
            if item.strip() == "":
                continue
            values.append(_coerce_sweep_scalar(item))
        elif isinstance(item, (bool, int, float)):
            values.append(item)
        else:
            values.append(str(item))
    if not values:
        raise JobPayloadError(f"sweep param {param_name!r} has no values")
    return values


def _to_job_float(raw: Any, *, default: float, field: str, minimum: float) -> float:
    if raw in (None, ""):
        return default
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise JobPayloadError(f"{field} must be a number") from exc
    if value < minimum:
        raise JobPayloadError(f"{field} must be at least {minimum}")
    return value


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


def _coerce_string_list(raw: Any) -> list[str]:
    if raw is None or raw == "":
        return []
    items = raw if isinstance(raw, list) else [raw]
    seen: list[str] = []
    for item in items:
        if item is None:
            continue
        text = str(item).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def resolve_custom_research_body(connection: sqlite3.Connection, body: dict[str, Any]) -> dict[str, Any]:
    compare_strategies = bool(body.get("compare_strategies"))
    use_all_hourly_files = bool(body.get("use_all_hourly_files"))
    dataset_ids = body.get("dataset_ids")
    export_market_symbol = body.get("export_market_symbol")
    has_single_export = bool(export_market_symbol and str(export_market_symbol).strip())
    export_market_symbols = _coerce_string_list(body.get("export_market_symbols"))
    if has_single_export and str(export_market_symbol).strip() not in export_market_symbols:
        export_market_symbols.insert(0, str(export_market_symbol).strip())
    export_intervals = _coerce_string_list(body.get("export_intervals"))
    single_interval = str(body.get("interval") or "").strip()
    if single_interval and single_interval not in export_intervals:
        export_intervals.append(single_interval)
    has_batch_export = bool(export_market_symbols)
    if not compare_strategies:
        raise JobPayloadError("enable compare_strategies")
    if not use_all_hourly_files and not has_single_export and not has_batch_export:
        if not isinstance(dataset_ids, list) or not dataset_ids:
            raise JobPayloadError(
                "dataset_ids required unless export_market_symbol(s) or use_all_hourly_files",
            )

    prepared: dict[str, Any] = {
        "compare_strategies": compare_strategies,
        "use_all_hourly_files": use_all_hourly_files,
        "visualize": bool(body.get("visualize", True)),
        "cash": body.get("cash"),
        "fee": _to_job_float(body.get("fee"), default=0.0, field="fee", minimum=0.0),
        "slippage": _to_job_float(body.get("slippage"), default=0.0, field="slippage", minimum=0.0),
        "vectorbt": body.get("vectorbt"),
        "compare_mode": body.get("compare_mode") or "strategies",
    }
    if prepared["fee"] >= 1:
        raise JobPayloadError("fee must be below 1 (fraction, e.g. 0.001 for 0.1%)")
    if prepared["slippage"] >= 1:
        raise JobPayloadError("slippage must be below 1 (fraction, e.g. 0.0005)")
    execution = str(body.get("execution") or "close").strip().lower()
    if execution not in ("close", "next_open"):
        raise JobPayloadError("execution must be close or next_open")
    prepared["execution"] = execution

    raw_export_days = body.get("export_days")
    try:
        export_days = int(raw_export_days if raw_export_days not in (None, "") else 30)
    except (TypeError, ValueError) as exc:
        raise JobPayloadError("export_days must be an integer") from exc
    if export_days < 1:
        raise JobPayloadError("export_days must be at least 1")
    days_by_interval: dict[str, int] = {}
    raw_days_map = body.get("export_days_by_interval")
    if isinstance(raw_days_map, dict):
        for raw_interval, raw_days in raw_days_map.items():
            interval_key = str(raw_interval).strip()
            if not interval_key or raw_days in (None, ""):
                continue
            try:
                interval_days = int(raw_days)
            except (TypeError, ValueError) as exc:
                raise JobPayloadError(
                    f"export_days_by_interval[{interval_key!r}] must be an integer"
                ) from exc
            if interval_days < 1:
                raise JobPayloadError(f"export_days_by_interval[{interval_key!r}] must be at least 1")
            days_by_interval[interval_key] = interval_days

    raw_steps = body.get("export_steps")
    try:
        export_steps = int(raw_steps) if raw_steps not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise JobPayloadError("export_steps must be an integer") from exc
    if export_steps is not None and export_steps < 1:
        raise JobPayloadError("export_steps must be at least 1")
    steps_by_interval: dict[str, int] = {}
    raw_steps_map = body.get("export_steps_by_interval")
    if isinstance(raw_steps_map, dict):
        for raw_interval, raw_interval_steps in raw_steps_map.items():
            interval_key = str(raw_interval).strip()
            if not interval_key or raw_interval_steps in (None, ""):
                continue
            try:
                interval_steps = int(raw_interval_steps)
            except (TypeError, ValueError) as exc:
                raise JobPayloadError(
                    f"export_steps_by_interval[{interval_key!r}] must be an integer"
                ) from exc
            if interval_steps < 1:
                raise JobPayloadError(f"export_steps_by_interval[{interval_key!r}] must be at least 1")
            steps_by_interval[interval_key] = interval_steps

    def _steps_for_interval(interval: str) -> int | None:
        return steps_by_interval.get(str(interval).strip(), export_steps)

    def _days_for_interval(interval: str) -> int:
        explicit = days_by_interval.get(str(interval).strip())
        if explicit is not None:
            return explicit
        steps = _steps_for_interval(interval)
        if steps is not None:
            try:
                minutes = resolution_minutes(str(interval).strip())
            except ValueError as exc:
                raise JobPayloadError(f"unknown interval for steps sizing: {interval!r}") from exc
            return math.ceil(steps * minutes / 1440) + 1
        return export_days

    def _trim_for_interval(interval: str) -> int | None:
        if str(interval).strip() in days_by_interval:
            return None
        return _steps_for_interval(interval)

    if has_single_export and not has_batch_export:
        prepared["export_days"] = export_days
        export_body = dict(body)
        export_body["market_symbol"] = str(export_market_symbol).strip()
        if not export_body.get("interval"):
            export_body["interval"] = "60"
        export_body["days"] = _days_for_interval(str(export_body.get("interval")))
        export_body["max_bars"] = _trim_for_interval(str(export_body.get("interval")))
        if not export_body.get("out"):
            export_body["out"] = "data"
        prepared["export_fields"] = resolve_export_argv_fields(connection, export_body)
    if has_batch_export:
        if not export_intervals:
            export_intervals = ["60"]
        if len(export_market_symbols) * len(export_intervals) > 24:
            raise JobPayloadError("too many market × horizon combos (max 24 per run)")
        prepared["export_days"] = export_days
        prepared["export_days_by_interval"] = days_by_interval
        export_jobs: list[dict[str, Any]] = []
        for market_symbol in export_market_symbols:
            for interval in export_intervals:
                export_body = dict(body)
                export_body["market_symbol"] = market_symbol
                export_body["interval"] = interval
                export_body["days"] = _days_for_interval(interval)
                export_body["max_bars"] = _trim_for_interval(interval)
                if not export_body.get("out"):
                    export_body["out"] = "data"
                export_jobs.append(resolve_export_argv_fields(connection, export_body))
        prepared["export_jobs"] = export_jobs

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
            "max_bars": body.get("max_bars"),
            "out": body.get("out"),
            "crypto_layout": body.get("crypto_layout"),
        }
    return {
        "src": body.get("src"),
        "dst": body.get("dst"),
        "interval": body.get("interval"),
        "days": body.get("days"),
        "max_bars": body.get("max_bars"),
        "out": body.get("out"),
        "crypto_layout": body.get("crypto_layout"),
    }
