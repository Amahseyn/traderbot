from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from traderbot.algorithms.registry import strategy_param_names
from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest, robust_params_for
from traderbot.utils.resolution import resolution_from_csv_path


def default_database_path() -> Path:
    raw = os.environ.get("TRADERBOT_DB", "").strip()
    if raw:
        return Path(raw)
    return Path("data/traderbot.db")


def symbol_from_csv_path(csv_path: Path | str) -> str:
    path = Path(csv_path)
    resolution = resolution_from_csv_path(path.name)
    suffix = f"_{resolution}"
    stem = path.stem
    if stem.endswith(suffix):
        return stem[: -len(suffix)].upper()
    return stem.upper()


def best_sweep_params_from_db(
    strategy_id: str,
    *,
    symbol: str | None,
    resolution: str | None,
    database_path: Path | str | None = None,
) -> dict[str, Any] | None:
    if not symbol:
        return None
    db_path = Path(database_path) if database_path is not None else default_database_path()
    if not db_path.is_file():
        return None
    clauses = ["strategy_id = ?"]
    params: list[Any] = [strategy_id]
    clauses.append("symbol = ?")
    params.append(symbol.upper())
    if resolution:
        clauses.append("resolution = ?")
        params.append(str(resolution))
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            f"SELECT best_params_json FROM sweep_sessions WHERE {' AND '.join(clauses)}"
            " ORDER BY created_at_utc DESC LIMIT 1",
            params,
        ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def resolve_optimized_namespace(
    strategy_id: str,
    base: Any | None = None,
    *,
    csv_path: Path | str | None = None,
    symbol: str | None = None,
    resolution: str | None = None,
    defaults_file: Path | str | None = None,
    database_path: Path | str | None = None,
) -> Any:
    """Robust tuned defaults, then latest sweep winner for symbol × resolution when present."""
    namespace = namespace_for_strategy_backtest(
        strategy_id,
        base,
        csv_path=csv_path,
        defaults_file=defaults_file,
        resolution=resolution,
    )
    market_symbol = symbol
    if market_symbol is None and csv_path is not None:
        market_symbol = symbol_from_csv_path(csv_path)
    bar_resolution = resolution
    if bar_resolution is None and csv_path is not None:
        try:
            bar_resolution = resolution_from_csv_path(Path(csv_path).name)
        except (ValueError, IndexError):
            bar_resolution = None
    sweep_params = best_sweep_params_from_db(
        strategy_id,
        symbol=market_symbol,
        resolution=bar_resolution,
        database_path=database_path,
    )
    if sweep_params:
        for name, value in sweep_params.items():
            if hasattr(namespace, name):
                setattr(namespace, name, value)
    return namespace


def optimized_strategy_values(
    strategy_id: str,
    *,
    symbol: str | None = None,
    resolution: str | None = None,
    csv_path: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, str]]:
    """Resolved knob values and per-field source labels for Lab UI."""
    names = strategy_param_names(strategy_id)
    market_symbol = symbol
    if market_symbol is None and csv_path is not None:
        market_symbol = symbol_from_csv_path(csv_path)
    bar_resolution = resolution
    if bar_resolution is None and csv_path is not None:
        try:
            bar_resolution = resolution_from_csv_path(Path(csv_path).name)
        except (ValueError, IndexError):
            bar_resolution = None

    robust = robust_params_for(strategy_id, resolution=bar_resolution, horizon_label=None) or {}
    sweep = (
        best_sweep_params_from_db(strategy_id, symbol=market_symbol, resolution=bar_resolution) or {}
    )
    namespace = resolve_optimized_namespace(
        strategy_id,
        None,
        csv_path=csv_path,
        symbol=market_symbol,
        resolution=bar_resolution,
    )
    values = {name: getattr(namespace, name) for name in names if hasattr(namespace, name)}
    sources: dict[str, str] = {}
    for name in names:
        if name in sweep:
            sources[name] = "sweep"
        elif name in robust:
            sources[name] = "robust"
        else:
            sources[name] = "default"
    return values, sources
