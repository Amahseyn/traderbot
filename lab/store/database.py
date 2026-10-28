from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from lab.store.constants import REPO_ROOT
from lab.store.schema import CREATE_TABLES_SQL, SCHEMA_VERSION


def default_database_path() -> Path:
    raw = os.environ.get("TRADERBOT_DB", "").strip()
    if raw:
        return Path(raw)
    return REPO_ROOT / "data" / "traderbot.db"


def open_database(database_path: Path | None = None) -> sqlite3.Connection:
    path = database_path or default_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    init_database(connection)
    return connection


_DATASET_EXTRA_COLUMNS = ("horizon_label", "range_start_utc", "range_end_utc")

_SWEEP_EXTRA_COLUMNS = (
    "optimize_start_utc",
    "optimize_end_utc",
    "compare_start_utc",
    "compare_end_utc",
)


def ensure_discovery_columns(connection: sqlite3.Connection) -> None:
    """Add full report blob for discovery runs (CoinBeacon snapshots)."""
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'discovery_runs'",
    ).fetchone()
    if table is None:
        return
    present = {row[1] for row in connection.execute("PRAGMA table_info(discovery_runs)")}
    if "report_json" not in present:
        connection.execute("ALTER TABLE discovery_runs ADD COLUMN report_json TEXT")


def ensure_sweep_columns(connection: sqlite3.Connection) -> None:
    """Add optimizer fit / compare window columns on databases created before schema 6."""
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sweep_sessions'",
    ).fetchone()
    if table is None:
        return
    present = {row[1] for row in connection.execute("PRAGMA table_info(sweep_sessions)")}
    for column in _SWEEP_EXTRA_COLUMNS:
        if column not in present:
            connection.execute(f"ALTER TABLE sweep_sessions ADD COLUMN {column} TEXT")


def ensure_dataset_columns(connection: sqlite3.Connection) -> None:
    """Add horizon and date-range columns on databases created before schema 3."""
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'datasets'",
    ).fetchone()
    if table is None:
        return
    present = {row[1] for row in connection.execute("PRAGMA table_info(datasets)")}
    for column in _DATASET_EXTRA_COLUMNS:
        if column not in present:
            connection.execute(f"ALTER TABLE datasets ADD COLUMN {column} TEXT")


def backfill_sweep_horizon_labels(connection: sqlite3.Connection) -> int:
    """Label sweeps recorded before horizon folders were part of the key; returns rows updated."""
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sweep_sessions'",
    ).fetchone()
    if table is None:
        return 0
    present = {row[1] for row in connection.execute("PRAGMA table_info(sweep_sessions)")}
    if "horizon_label" not in present:
        return 0
    from traderbot.data.crypto_store import horizon_label_from_csv_dir

    rows = connection.execute(
        "SELECT DISTINCT csv_path FROM sweep_sessions"
        " WHERE csv_path IS NOT NULL AND (horizon_label IS NULL OR horizon_label = '')",
    ).fetchall()
    updated = 0
    for row in rows:
        csv_path = str(row[0] or "")
        if not csv_path:
            continue
        label = horizon_label_from_csv_dir(Path(csv_path).parent)
        if not label:
            continue
        cursor = connection.execute(
            "UPDATE sweep_sessions SET horizon_label = ?"
            " WHERE csv_path = ? AND (horizon_label IS NULL OR horizon_label = '')",
            (label, csv_path),
        )
        updated += cursor.rowcount
    return updated


def _migrate_schema(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'",
    ).fetchone()
    previous = int(row[0]) if row is not None else 0
    if previous < 4:
        from lab.store.catalog import CATALOG_SCOPE_DEFAULT_JOBS, refresh_market_catalog

        refresh_market_catalog(connection, catalog_scope=CATALOG_SCOPE_DEFAULT_JOBS)
    if previous < 8:
        backfill_sweep_horizon_labels(connection)


def ensure_marketcap_tables(connection: sqlite3.Connection) -> None:
    """Ensure marketcap_cache table exists on databases created with earlier schemas."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS marketcap_cache (
            cache_key TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL
        )
        """
    )


def init_database(connection: sqlite3.Connection) -> None:
    connection.executescript(CREATE_TABLES_SQL)
    ensure_dataset_columns(connection)
    ensure_sweep_columns(connection)
    ensure_discovery_columns(connection)
    ensure_marketcap_tables(connection)
    _migrate_schema(connection)
    row = connection.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'",
    ).fetchone()
    stored_version = int(row[0]) if row is not None else 0
    if stored_version != SCHEMA_VERSION:
        connection.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
            ("schema_version", str(SCHEMA_VERSION)),
        )
        connection.commit()
