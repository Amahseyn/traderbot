from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from traderbot.algorithms.registry import strategy_param_names
from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest, robust_params_for
from traderbot.utils.resolution import resolution_from_csv_path

FALLBACK_SWEEP_SYMBOLS_RLS = ("BTCIRT", "ETHIRT")
FALLBACK_SWEEP_SYMBOLS_USDT = ("BTCUSDT", "ETHUSDT")


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


def quote_bucket_for_symbol(symbol: str) -> str:
    upper = symbol.strip().upper()
    if upper.endswith("USDT"):
        return "usdt"
    return "rls"


def fallback_sweep_symbols(symbol: str) -> tuple[str, ...]:
    if quote_bucket_for_symbol(symbol) == "usdt":
        return FALLBACK_SWEEP_SYMBOLS_USDT
    return FALLBACK_SWEEP_SYMBOLS_RLS


def sweep_symbol_candidates(symbol: str) -> tuple[str, ...]:
    primary = symbol.strip().upper()
    ordered: list[str] = []
    seen: set[str] = set()
    for candidate in (primary, *fallback_sweep_symbols(primary)):
        key = candidate.upper()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


def _fetch_sweep_params_row(
    connection: sqlite3.Connection,
    strategy_id: str,
    *,
    symbol: str,
    resolution: str | None,
) -> dict[str, Any] | None:
    clauses = ["strategy_id = ?", "symbol = ?"]
    params: list[Any] = [strategy_id, symbol.upper()]
    if resolution:
        clauses.append("resolution = ?")
        params.append(str(resolution))
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


def resolve_best_sweep_params(
    strategy_id: str,
    *,
    symbol: str | None,
    resolution: str | None,
    database_path: Path | str | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Latest sweep winner for this market, else the same strategy on a default liquid pair."""
    if not symbol:
        return None, None
    db_path = Path(database_path) if database_path is not None else default_database_path()
    if not db_path.is_file():
        return None, None
    with sqlite3.connect(db_path) as connection:
        for candidate in sweep_symbol_candidates(symbol):
            params = _fetch_sweep_params_row(
                connection,
                strategy_id,
                symbol=candidate,
                resolution=resolution,
            )
            if params:
                return params, candidate.upper()
    return None, None


def best_sweep_params_from_db(
    strategy_id: str,
    *,
    symbol: str | None,
    resolution: str | None,
    database_path: Path | str | None = None,
) -> dict[str, Any] | None:
    params, _symbol = resolve_best_sweep_params(
        strategy_id,
        symbol=symbol,
        resolution=resolution,
        database_path=database_path,
    )
    return params


def resolve_optimized_namespace(
    strategy_id: str,
    base: Any | None = None,
    *,
    csv_path: Path | str | None = None,
    symbol: str | None = None,
    resolution: str | None = None,
    defaults_file: Path | str | None = None,
    database_path: Path | str | None = None,
    apply_sweep_winner: bool = False,
) -> Any:
    """Robust tuned defaults; sweep winner only when ``apply_sweep_winner`` is explicitly set."""
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
    if apply_sweep_winner:
        sweep_params, _matched = resolve_best_sweep_params(
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
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    """Resolved knob values, per-field source labels, and sweep metadata for Lab UI."""
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
    sweep_params, sweep_symbol = resolve_best_sweep_params(
        strategy_id,
        symbol=market_symbol,
        resolution=bar_resolution,
    )
    sweep = sweep_params or {}
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
            if (
                market_symbol
                and sweep_symbol
                and sweep_symbol.upper() != market_symbol.upper()
            ):
                sources[name] = "sweep_fallback"
            else:
                sources[name] = "sweep"
        elif name in robust:
            sources[name] = "robust"
        else:
            sources[name] = "default"
    meta = {
        "requested_symbol": market_symbol.upper() if market_symbol else None,
        "sweep_symbol": sweep_symbol,
        "sweep_fallback": bool(
            market_symbol
            and sweep_symbol
            and sweep_symbol.upper() != market_symbol.upper()
        ),
    }
    return values, sources, meta
