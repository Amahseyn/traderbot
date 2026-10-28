from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from traderbot.algorithms.registry import strategy_param_names
from traderbot.algorithms.strategy_defaults import (
    horizon_bucket_label_for_csv,
    namespace_for_strategy_backtest,
    robust_params_for,
)
from traderbot.data.crypto_store import horizon_label_from_csv_dir
from traderbot.utils.resolution import resolution_from_csv_path

logger = logging.getLogger(__name__)

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


def horizon_label_from_csv_path(csv_path: Path | str | None) -> str | None:
    """Horizon folder label for a dataset path (``.../horizons/12h/SYM_60.csv`` → ``12h``)."""
    if csv_path is None:
        return None
    return horizon_label_from_csv_dir(Path(csv_path).parent)


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


def _sweep_sessions_window_columns(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute("PRAGMA table_info(sweep_sessions)").fetchall()
    return {str(row[1]) for row in rows}


def _iso_utc_to_unix(value: Any) -> int | None:
    """Parse an ISO 8601 UTC timestamp (``...Z`` or ``+00:00``) to unix seconds."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        normalised = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalised)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.astimezone(timezone.utc).timestamp())
    except (ValueError, TypeError):
        return None


def _record_is_temporally_eligible(
    record: dict[str, Any],
    *,
    run_start_unix_seconds: int | None,
) -> bool:
    """True when the sweep's fit window ends before the evaluation run starts.

    A sweep trained on data that overlaps the compare/evaluation window would
    apply overfitted parameters to the very bars it was fitted on.  When the
    caller supplies ``run_start_unix_seconds``, records whose
    ``optimize_end_utc`` is at or after that start are rejected.
    """
    if run_start_unix_seconds is None:
        return True
    fit_end = _iso_utc_to_unix(record.get("optimize_end_utc"))
    if fit_end is None:
        # No timestamp recorded — conservatively allow it to preserve legacy behaviour.
        return True
    return fit_end < int(run_start_unix_seconds)


def _sweep_horizon_tiers(
    horizon_label: str | None,
    columns: set[str],
) -> list[tuple[str | None, list[Any]]]:
    """Horizon filters in lookup order: exact label, then unlabeled rows, then any row."""
    if "horizon_label" not in columns:
        return [(None, [])]
    tiers: list[tuple[str | None, list[Any]]] = []
    label = str(horizon_label or "").strip()
    if label:
        tiers.append(("horizon_label = ?", [label]))
    tiers.append(("(horizon_label IS NULL OR horizon_label = '')", []))
    tiers.append((None, []))
    return tiers


def _fetch_sweep_record_row(
    connection: sqlite3.Connection,
    strategy_id: str,
    *,
    symbol: str,
    resolution: str | None,
    horizon_label: str | None = None,
    run_start_unix_seconds: int | None = None,
) -> dict[str, Any] | None:
    columns = _sweep_sessions_window_columns(connection)
    base_clauses = ["strategy_id = ?", "symbol = ?"]
    base_params: list[Any] = [strategy_id, symbol.upper()]
    if resolution:
        base_clauses.append("resolution = ?")
        base_params.append(str(resolution))
    extra_names: list[str] = []
    if "horizon_label" in columns:
        extra_names.append("horizon_label")
    if "optimize_start_utc" in columns:
        extra_names.extend(
            ("optimize_start_utc", "optimize_end_utc", "compare_start_utc", "compare_end_utc")
        )
    extra_select = "".join(f", {name}" for name in extra_names)
    # Temporal guard: reject sweep records whose fit window overlaps the
    # evaluation window.  ``optimize_end_utc`` is stored as an ISO 8601 string;
    # ISO 8601 UTC timestamps sort lexicographically, so a ``<`` comparison in
    # SQL is correct when both operands are normalised to ``Z``-suffixed form.
    fit_end_clause = ""
    if run_start_unix_seconds is not None and "optimize_end_utc" in columns:
        from traderbot.backtesting.bar_windows import unix_to_utc_iso

        fit_end_clause = " AND (optimize_end_utc IS NULL OR optimize_end_utc < ?)"
        base_params.append(unix_to_utc_iso(int(run_start_unix_seconds)))
    row = None
    for horizon_clause, horizon_params in _sweep_horizon_tiers(horizon_label, columns):
        clauses = list(base_clauses)
        params = list(base_params)
        if horizon_clause is not None:
            clauses.append(horizon_clause)
            params.extend(horizon_params)
        row = connection.execute(
            f"SELECT best_params_json{extra_select} FROM sweep_sessions "
            f"WHERE {' AND '.join(clauses)}{fit_end_clause}"
            " ORDER BY created_at_utc DESC LIMIT 1",
            params,
        ).fetchone()
        if row is not None:
            break
    if row is None:
        return None
    try:
        payload = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    record: dict[str, Any] = {"best_params": dict(payload)}
    for offset, name in enumerate(extra_names, start=1):
        record[name] = row[offset]
    return record


def resolve_best_sweep_record(
    strategy_id: str,
    *,
    symbol: str | None,
    resolution: str | None,
    horizon_label: str | None = None,
    database_path: Path | str | None = None,
    run_start_unix_seconds: int | None = None,
) -> dict[str, Any] | None:
    """Latest sweep row for this market (or liquid fallback), including fit/compare windows.

    When ``run_start_unix_seconds`` is set, sweep records whose fit window
    (``optimize_end_utc``) overlaps the evaluation run are rejected to prevent
    temporal leakage — a sweep trained on bars that include the evaluation
    window would apply overfitted parameters to that very window.
    """
    if not symbol:
        return None
    db_path = Path(database_path) if database_path is not None else default_database_path()
    if not db_path.is_file():
        return None
    with sqlite3.connect(db_path) as connection:
        for candidate in sweep_symbol_candidates(symbol):
            record = _fetch_sweep_record_row(
                connection,
                strategy_id,
                symbol=candidate,
                resolution=resolution,
                horizon_label=horizon_label,
                run_start_unix_seconds=run_start_unix_seconds,
            )
            if record is not None:
                record["symbol"] = candidate.upper()
                return record
    return None


def resolve_best_sweep_params(
    strategy_id: str,
    *,
    symbol: str | None,
    resolution: str | None,
    horizon_label: str | None = None,
    database_path: Path | str | None = None,
    run_start_unix_seconds: int | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """Latest sweep winner for this market, else the same strategy on a default liquid pair."""
    record = resolve_best_sweep_record(
        strategy_id,
        symbol=symbol,
        resolution=resolution,
        horizon_label=horizon_label,
        database_path=database_path,
        run_start_unix_seconds=run_start_unix_seconds,
    )
    if record is None:
        return None, None
    return dict(record["best_params"]), str(record["symbol"])


def best_sweep_params_from_db(
    strategy_id: str,
    *,
    symbol: str | None,
    resolution: str | None,
    horizon_label: str | None = None,
    database_path: Path | str | None = None,
    run_start_unix_seconds: int | None = None,
) -> dict[str, Any] | None:
    params, _symbol = resolve_best_sweep_params(
        strategy_id,
        symbol=symbol,
        resolution=resolution,
        horizon_label=horizon_label,
        database_path=database_path,
        run_start_unix_seconds=run_start_unix_seconds,
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
    run_start_unix_seconds: int | None = None,
) -> Any:
    """Robust tuned defaults; sweep winner only when ``apply_sweep_winner`` is explicitly set.

    When ``run_start_unix_seconds`` is provided alongside ``apply_sweep_winner``,
    only sweep records whose fit window ends before the evaluation start are
    applied, preventing temporal leakage from overfitted, overlapping-window params.
    """
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
            horizon_label=horizon_label_from_csv_path(csv_path),
            database_path=database_path,
            run_start_unix_seconds=run_start_unix_seconds,
        )
        if sweep_params:
            for name, value in sweep_params.items():
                if hasattr(namespace, name):
                    setattr(namespace, name, value)
        elif run_start_unix_seconds is not None:
            logger.info(
                "resolve_optimized_namespace: no temporally-eligible sweep record for "
                "strategy=%s symbol=%s run_start=%s; falling back to robust defaults",
                strategy_id,
                market_symbol,
                run_start_unix_seconds,
            )
    return namespace


def optimized_strategy_values(
    strategy_id: str,
    *,
    symbol: str | None = None,
    resolution: str | None = None,
    csv_path: Path | str | None = None,
    horizon_label: str | None = None,
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
    resolved_horizon = horizon_label or horizon_label_from_csv_path(csv_path)

    robust = robust_params_for(
        strategy_id,
        resolution=bar_resolution,
        horizon_label=horizon_bucket_label_for_csv(csv_path),
    ) or {}
    sweep_record = resolve_best_sweep_record(
        strategy_id,
        symbol=market_symbol,
        resolution=bar_resolution,
        horizon_label=resolved_horizon,
    )
    sweep_params = sweep_record["best_params"] if sweep_record else None
    sweep_symbol = sweep_record["symbol"] if sweep_record else None
    sweep = sweep_params or {}
    namespace = resolve_optimized_namespace(
        strategy_id,
        None,
        csv_path=csv_path,
        symbol=market_symbol,
        resolution=bar_resolution,
    )
    for name, value in sweep.items():
        if hasattr(namespace, name):
            setattr(namespace, name, value)
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
        "sweep_horizon_label": sweep_record.get("horizon_label") if sweep_record else None,
        "sweep_fallback": bool(
            market_symbol
            and sweep_symbol
            and sweep_symbol.upper() != market_symbol.upper()
        ),
        "optimize_start_utc": sweep_record.get("optimize_start_utc") if sweep_record else None,
        "optimize_end_utc": sweep_record.get("optimize_end_utc") if sweep_record else None,
        "compare_start_utc": sweep_record.get("compare_start_utc") if sweep_record else None,
        "compare_end_utc": sweep_record.get("compare_end_utc") if sweep_record else None,
    }
    return values, sources, meta
