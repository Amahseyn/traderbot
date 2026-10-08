from __future__ import annotations

import sqlite3
from pathlib import Path

from lab.store.constants import REPO_ROOT
from lab.store.schema import CREATE_TABLES_SQL, SCHEMA_VERSION


def default_database_path() -> Path:
    return REPO_ROOT / "data" / "traderbot.db"


def open_database(database_path: Path | None = None) -> sqlite3.Connection:
    path = database_path or default_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    init_database(connection)
    return connection


_DATASET_EXTRA_COLUMNS = ("horizon_label", "range_start_utc", "range_end_utc")


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


def _migrate_schema(connection: sqlite3.Connection) -> None:
    row = connection.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'",
    ).fetchone()
    previous = int(row[0]) if row is not None else 0
    if previous < 4:
        from lab.store.catalog import CATALOG_SCOPE_DEFAULT_JOBS, refresh_market_catalog

        refresh_market_catalog(connection, catalog_scope=CATALOG_SCOPE_DEFAULT_JOBS)


def init_database(connection: sqlite3.Connection) -> None:
    connection.executescript(CREATE_TABLES_SQL)
    ensure_dataset_columns(connection)
    _migrate_schema(connection)
    connection.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
        ("schema_version", str(SCHEMA_VERSION)),
    )
    connection.commit()
