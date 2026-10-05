from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from traderbot.data.crypto_store import horizon_label_from_csv_dir
from traderbot.markets.registry import DEFAULT_JOBS_PATH, markets_catalog_dict
from lab.store.canonical import parse_symbol_resolution_from_csv
from lab.store.constants import REPO_ROOT
from lab.store.database import ensure_dataset_columns

CATALOG_SCOPE_DEFAULT_JOBS = "default_jobs"
CATALOG_SCOPE_NOBITEX_ALL = "nobitex_all"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def dataset_id_for_repo_path(repo_path: str) -> str:
    normalized = str(Path(repo_path).as_posix())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def canonical_dataset_repo_path(repo_path: str) -> str:
    raw = Path(repo_path)
    absolute = raw.resolve() if raw.is_absolute() else (REPO_ROOT / raw).resolve()
    try:
        return absolute.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return absolute.as_posix()


def resolve_dataset_csv(repo_path: str) -> Path | None:
    raw = Path(repo_path)
    candidates = [raw] if raw.is_absolute() else [REPO_ROOT / raw, raw]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def _cell_at(line: str, column_index: int) -> str | None:
    if not line.strip():
        return None
    cells = next(csv.reader([line]))
    if column_index >= len(cells):
        return None
    return cells[column_index].strip()


def _calendar_day(cell: str, *, kind: str) -> str | None:
    if not cell:
        return None
    if kind == "datetime":
        day = cell.split("T", 1)[0]
        if len(day) == 10 and day[4] == "-" and day[7] == "-":
            return day
        return None
    if cell.isdigit():
        instant = datetime.fromtimestamp(int(cell), tz=timezone.utc)
        return instant.date().isoformat()
    if len(cell) >= 10 and cell[4] == "-" and cell[7] == "-":
        return cell[:10]
    return None


def _last_text_line(csv_path: Path) -> str:
    with csv_path.open("rb") as handle:
        handle.seek(0, 2)
        cursor = handle.tell() - 1
        if cursor < 0:
            return ""
        buffer = bytearray()
        while cursor >= 0:
            handle.seek(cursor)
            byte = handle.read(1)
            if byte == b"\n" and buffer:
                break
            if byte not in (b"\n", b"\r"):
                buffer.append(byte[0])
            cursor -= 1
    return buffer[::-1].decode("utf-8").strip()


def load_csv_calendar_bounds(csv_path: Path) -> tuple[str | None, str | None]:
    """First and last calendar days in an OHLC CSV (``datetime_utc`` or ``timestamp``)."""
    if not csv_path.is_file():
        return None, None
    with csv_path.open(encoding="utf-8", newline="") as handle:
        header = handle.readline()
        if not header:
            return None, None
        columns = next(csv.reader([header]))
        if "datetime_utc" in columns:
            column_index = columns.index("datetime_utc")
            kind = "datetime"
        elif "timestamp" in columns:
            column_index = columns.index("timestamp")
            kind = "timestamp"
        else:
            return None, None
        first_line = handle.readline()
    start = _calendar_day(_cell_at(first_line, column_index) or "", kind=kind)
    end = _calendar_day(_cell_at(_last_text_line(csv_path), column_index) or "", kind=kind)
    if start and end and start > end:
        start, end = end, start
    return start, end


def build_dataset_label(
    *,
    symbol: str | None,
    resolution: str | None,
    repo_path: str,
    horizon_label: str | None = None,
    range_start_utc: str | None = None,
    range_end_utc: str | None = None,
) -> str:
    if symbol and resolution:
        name = f"{symbol} · {resolution}"
    else:
        parsed_symbol, parsed_resolution = parse_symbol_resolution_from_csv(repo_path)
        if parsed_symbol and parsed_resolution:
            name = f"{parsed_symbol} · {parsed_resolution}"
        else:
            name = Path(repo_path).stem
    parts = [name]
    if horizon_label:
        parts.append(f"horizon {horizon_label}")
    if range_start_utc and range_end_utc:
        parts.append(f"{range_start_utc} to {range_end_utc}")
    elif range_start_utc:
        parts.append(range_start_utc)
    return " · ".join(parts)


def _dataset_rows_for_file(
    connection: sqlite3.Connection,
    stored_path: str,
    resolved: Path | None,
) -> list[sqlite3.Row]:
    rows = connection.execute(
        "SELECT id, repo_path, source, registered_at_utc FROM datasets",
    ).fetchall()
    matches: list[sqlite3.Row] = []
    for row in rows:
        if row["repo_path"] == stored_path:
            matches.append(row)
            continue
        if resolved is None:
            continue
        other = resolve_dataset_csv(str(row["repo_path"]))
        if other is not None and other == resolved:
            matches.append(row)
    return matches


def upsert_dataset(
    connection: sqlite3.Connection,
    *,
    repo_path: str,
    source: str,
    symbol: str | None = None,
    resolution: str | None = None,
) -> str:
    ensure_dataset_columns(connection)
    stored_path = canonical_dataset_repo_path(repo_path)
    parsed_symbol, parsed_resolution = parse_symbol_resolution_from_csv(stored_path)
    symbol = (symbol or parsed_symbol or "").upper() or None
    resolution = resolution or parsed_resolution
    resolved = resolve_dataset_csv(stored_path)
    horizon_label = horizon_label_from_csv_dir(resolved.parent) if resolved is not None else None
    range_start_utc, range_end_utc = (
        load_csv_calendar_bounds(resolved) if resolved is not None else (None, None)
    )
    label = build_dataset_label(
        symbol=symbol,
        resolution=resolution,
        repo_path=stored_path,
        horizon_label=horizon_label,
        range_start_utc=range_start_utc,
        range_end_utc=range_end_utc,
    )
    now = _utc_now()
    dataset_id = dataset_id_for_repo_path(stored_path)
    matches = _dataset_rows_for_file(connection, stored_path, resolved)
    if matches:
        keeper = next((row for row in matches if row["repo_path"] == stored_path), None)
        if keeper is None:
            keeper = min(matches, key=lambda row: str(row["registered_at_utc"]))
        for row in matches:
            if row["id"] != keeper["id"]:
                connection.execute("DELETE FROM datasets WHERE id = ?", (row["id"],))
        kept_source = keeper["source"] if source == "data_file" else source
        connection.execute(
            """
            UPDATE datasets SET
                label = ?,
                symbol = ?,
                resolution = ?,
                horizon_label = ?,
                range_start_utc = ?,
                range_end_utc = ?,
                repo_path = ?,
                source = ?,
                last_seen_at_utc = ?
            WHERE id = ?
            """,
            (
                label,
                symbol,
                resolution,
                horizon_label,
                range_start_utc,
                range_end_utc,
                stored_path,
                kept_source,
                now,
                keeper["id"],
            ),
        )
        return str(keeper["id"])
    connection.execute(
        """
        INSERT INTO datasets (
            id, label, symbol, resolution, horizon_label, range_start_utc, range_end_utc,
            repo_path, source, registered_at_utc, last_seen_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dataset_id,
            label,
            symbol,
            resolution,
            horizon_label,
            range_start_utc,
            range_end_utc,
            stored_path,
            source,
            now,
            now,
        ),
    )
    return dataset_id


def register_data_csv_files(connection: sqlite3.Connection, data_root: Path | None = None) -> int:
    """Register every OHLC CSV under ``data/`` so catalog names stay in sync with disk."""
    root = data_root if data_root is not None else REPO_ROOT / "data"
    if not root.is_dir():
        return 0
    registered = 0
    for csv_path in sorted(root.rglob("*.csv")):
        if not csv_path.is_file():
            continue
        upsert_dataset(connection, repo_path=str(csv_path.resolve()), source="data_file")
        registered += 1
    return registered


def _path_is_in_repo(repo_path: str) -> bool:
    raw = Path(repo_path)
    absolute = raw.resolve() if raw.is_absolute() else (REPO_ROOT / raw).resolve()
    try:
        absolute.relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return True


def drop_missing_datasets(connection: sqlite3.Connection) -> int:
    """Remove catalog rows that point outside the repo at a file that is gone."""
    removed = 0
    rows = connection.execute("SELECT id, repo_path FROM datasets").fetchall()
    for row in rows:
        repo_path = str(row["repo_path"])
        if resolve_dataset_csv(repo_path) is not None or _path_is_in_repo(repo_path):
            continue
        connection.execute("DELETE FROM datasets WHERE id = ?", (row["id"],))
        removed += 1
    return removed


def backfill_datasets(connection: sqlite3.Connection) -> int:
    ensure_dataset_columns(connection)
    inserted = 0
    config_rows = connection.execute("SELECT data_context_json FROM configurations").fetchall()
    for row in config_rows:
        data_context = json.loads(row["data_context_json"])
        csv_path = data_context.get("csv")
        if not csv_path or resolve_dataset_csv(str(csv_path)) is None:
            continue
        upsert_dataset(
            connection,
            repo_path=str(csv_path),
            source="configuration",
            symbol=data_context.get("symbol"),
            resolution=data_context.get("resolution"),
        )
        inserted += 1
    compare_rows = connection.execute("SELECT csv_path FROM compare_sessions").fetchall()
    for row in compare_rows:
        csv_path = row["csv_path"]
        if not csv_path or resolve_dataset_csv(str(csv_path)) is None:
            continue
        upsert_dataset(connection, repo_path=str(csv_path), source="compare_session")
        inserted += 1
    inserted += register_data_csv_files(connection)
    drop_missing_datasets(connection)
    return inserted


def list_datasets(connection: sqlite3.Connection, *, limit: int = 200) -> list[dict[str, Any]]:
    capped = min(max(limit, 1), 500)
    rows = connection.execute(
        """
        SELECT id, label, symbol, resolution, horizon_label, range_start_utc, range_end_utc,
               source, last_seen_at_utc
        FROM datasets
        ORDER BY last_seen_at_utc DESC
        LIMIT ?
        """,
        (capped,),
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_dataset(connection: sqlite3.Connection, dataset_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT id, label, symbol, resolution, horizon_label, range_start_utc, range_end_utc,
               repo_path, source, registered_at_utc, last_seen_at_utc
        FROM datasets WHERE id = ?
        """,
        (dataset_id,),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def fetch_dataset_by_repo_path(connection: sqlite3.Connection, repo_path: str) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT id, label, symbol, resolution, horizon_label, range_start_utc, range_end_utc,
               repo_path, source, registered_at_utc, last_seen_at_utc
        FROM datasets WHERE repo_path = ?
        """,
        (str(Path(repo_path).as_posix()),),
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def dataset_public_view(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "label": row["label"],
        "symbol": row["symbol"],
        "resolution": row["resolution"],
        "horizon_label": row["horizon_label"],
        "range_start_utc": row["range_start_utc"],
        "range_end_utc": row["range_end_utc"],
        "source": row["source"],
        "last_seen_at_utc": row["last_seen_at_utc"],
    }


def refresh_market_catalog(
    connection: sqlite3.Connection,
    *,
    catalog_scope: str,
    jobs_path: Path | None = None,
) -> int:
    if catalog_scope == CATALOG_SCOPE_DEFAULT_JOBS:
        catalog = markets_catalog_dict(jobs_path or DEFAULT_JOBS_PATH)
    elif catalog_scope == CATALOG_SCOPE_NOBITEX_ALL:
        catalog = markets_catalog_dict(None)
    else:
        raise ValueError(f"unsupported catalog scope: {catalog_scope}")
    now = _utc_now()
    connection.execute("DELETE FROM market_catalog WHERE catalog_scope = ?", (catalog_scope,))
    for market in catalog["markets"]:
        connection.execute(
            """
            INSERT INTO market_catalog (symbol, src, dst, label, catalog_scope, updated_at_utc)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                market["symbol"],
                market["src"],
                market["dst"],
                market["label"],
                catalog_scope,
                now,
            ),
        )
    return len(catalog["markets"])


def ensure_default_jobs_catalog(connection: sqlite3.Connection) -> None:
    """Seed default export jobs markets into SQLite (local file only, no HTTP)."""
    jobs_count = connection.execute(
        "SELECT COUNT(*) FROM market_catalog WHERE catalog_scope = ?",
        (CATALOG_SCOPE_DEFAULT_JOBS,),
    ).fetchone()[0]
    if jobs_count == 0:
        refresh_market_catalog(connection, catalog_scope=CATALOG_SCOPE_DEFAULT_JOBS)


def ensure_market_catalog(connection: sqlite3.Connection) -> None:
    """Lab init/serve: local jobs file always; Nobitex clone is best-effort (offline-safe)."""
    ensure_default_jobs_catalog(connection)
    all_count = connection.execute(
        "SELECT COUNT(*) FROM market_catalog WHERE catalog_scope = ?",
        (CATALOG_SCOPE_NOBITEX_ALL,),
    ).fetchone()[0]
    if all_count == 0:
        try:
            refresh_market_catalog(connection, catalog_scope=CATALOG_SCOPE_NOBITEX_ALL)
        except Exception:
            pass


def load_market_catalog_scope(
    connection: sqlite3.Connection,
    *,
    catalog_scope: str,
    max_rows: int = 10_000,
) -> list[dict[str, Any]]:
    """All markets for a scope from SQLite (for UI client-side search)."""
    markets, _total = search_market_catalog(
        connection,
        catalog_scope=catalog_scope,
        query=None,
        limit=max_rows,
        offset=0,
    )
    return markets


def count_market_catalog(connection: sqlite3.Connection, *, catalog_scope: str) -> int:
    return int(
        connection.execute(
            "SELECT COUNT(*) FROM market_catalog WHERE catalog_scope = ?",
            (catalog_scope,),
        ).fetchone()[0],
    )


def market_catalog_updated_at(connection: sqlite3.Connection, *, catalog_scope: str) -> str | None:
    row = connection.execute(
        """
        SELECT MAX(updated_at_utc) AS updated_at_utc
        FROM market_catalog
        WHERE catalog_scope = ?
        """,
        (catalog_scope,),
    ).fetchone()
    if row is None or row["updated_at_utc"] is None:
        return None
    return str(row["updated_at_utc"])


def search_market_catalog(
    connection: sqlite3.Connection,
    *,
    catalog_scope: str,
    query: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    capped_limit = min(max(limit, 1), 500)
    safe_offset = max(offset, 0)
    params: list[Any] = [catalog_scope]
    where_clause = "catalog_scope = ?"
    trimmed_query = (query or "").strip()
    if trimmed_query:
        needle = f"%{trimmed_query.lower()}%"
        where_clause += (
            " AND (LOWER(symbol) LIKE ? OR LOWER(label) LIKE ?"
            " OR LOWER(src) LIKE ? OR LOWER(dst) LIKE ?)"
        )
        params.extend([needle, needle, needle, needle])
    total_count = connection.execute(
        f"SELECT COUNT(*) FROM market_catalog WHERE {where_clause}",
        params,
    ).fetchone()[0]
    page_params = [*params, capped_limit, safe_offset]
    rows = connection.execute(
        f"""
        SELECT symbol, src, dst, label, catalog_scope, updated_at_utc
        FROM market_catalog
        WHERE {where_clause}
        ORDER BY symbol
        LIMIT ? OFFSET ?
        """,
        page_params,
    ).fetchall()
    return [dict(row) for row in rows], int(total_count)


def list_market_catalog(
    connection: sqlite3.Connection,
    *,
    catalog_scope: str,
    limit: int = 500,
) -> list[dict[str, Any]]:
    markets, _total = search_market_catalog(
        connection,
        catalog_scope=catalog_scope,
        query=None,
        limit=limit,
        offset=0,
    )
    return markets


def fetch_market(
    connection: sqlite3.Connection,
    symbol: str,
    *,
    catalog_scope: str | None = None,
) -> dict[str, Any] | None:
    if catalog_scope:
        row = connection.execute(
            """
            SELECT symbol, src, dst, label, catalog_scope, updated_at_utc
            FROM market_catalog WHERE symbol = ? AND catalog_scope = ?
            """,
            (symbol.upper(), catalog_scope),
        ).fetchone()
    else:
        row = connection.execute(
            """
            SELECT symbol, src, dst, label, catalog_scope, updated_at_utc
            FROM market_catalog WHERE symbol = ?
            ORDER BY updated_at_utc DESC
            LIMIT 1
            """,
            (symbol.upper(),),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def expected_export_repo_path(*, symbol: str, interval: str, output_dir: str = "data") -> str:
    output_root = Path(output_dir.strip("/"))
    return str(output_root / f"{symbol.upper()}_{interval}.csv").replace("\\", "/")
