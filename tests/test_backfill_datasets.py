"""Regression tests for the /api/datasets backfill storm.

Every ``GET /api/datasets`` used to re-run a full filesystem + table scan inside one
long write transaction (~30s on the real repo). Overlapping poll requests then hit
``sqlite3.OperationalError: database is locked``. The catalog backfill must be cheap
on repeat requests, serialized in-process, and match dataset rows without per-row
filesystem stats.
"""

from pathlib import Path

import pytest

from lab.store.catalog import backfill_datasets, upsert_dataset
from lab.store.database import init_database, open_database

CSV_HEADER = "symbol,resolution,timestamp,datetime_utc,open,high,low,close,volume\n"


def _csv(path: Path, day: str = "2024-01-01") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        CSV_HEADER + f"TESTUSDT,60,0,{day}T00:00:00+00:00,1,1,1,1,1\n",
        encoding="utf-8",
    )


@pytest.fixture()
def dataset_connection(tmp_path: Path):
    connection = open_database(tmp_path / "lab.db")
    init_database(connection)
    yield connection
    connection.close()


def _write_sample_csvs(data_root: Path, file_count: int = 2) -> None:
    for index in range(file_count):
        _csv(data_root / f"TESTUSDT{index}_60.csv")


def test_backfill_datasets_registers_new_files(dataset_connection, tmp_path: Path):
    data_root = tmp_path / "data"
    _write_sample_csvs(data_root)
    assert backfill_datasets(dataset_connection, data_root=data_root) == 2
    rows = dataset_connection.execute("SELECT repo_path FROM datasets").fetchall()
    assert len(rows) == 2


def test_backfill_datasets_skips_when_data_unchanged(dataset_connection, tmp_path: Path):
    data_root = tmp_path / "data"
    _write_sample_csvs(data_root)
    assert backfill_datasets(dataset_connection, data_root=data_root) == 2

    # Nothing new on disk or in source tables: the repeat run must be skipped
    # (no fresh write transaction), not upsert all rows again.
    assert backfill_datasets(dataset_connection, data_root=data_root) == 0
    assert backfill_datasets(dataset_connection, data_root=data_root) == 0
    assert dataset_connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 2


def test_backfill_datasets_runs_after_data_changes(dataset_connection, tmp_path: Path):
    data_root = tmp_path / "data"
    _csv(data_root / "TESTUSDT_60.csv")
    assert backfill_datasets(dataset_connection, data_root=data_root) == 1
    assert backfill_datasets(dataset_connection, data_root=data_root) == 0

    # A newly exported file changes the catalog inputs and must be picked up.
    _csv(data_root / "TESTETHUSDT_60.csv")
    assert backfill_datasets(dataset_connection, data_root=data_root) == 1

    # A new configuration row referencing a dataset CSV triggers the source backfill too.
    dataset_connection.execute(
        "INSERT INTO configurations (id, config_kind, strategy_id, parameters_json, data_context_json, created_at_utc)"
        " VALUES ('cfg-1', 'sweep_best', 'rsi_threshold', '{}', ?, ?)",
        ("{\"csv\": \"TESTNEWUSDT_60.csv\"}", "2024-01-01T00:00:00+00:00"),
    )
    dataset_connection.commit()
    _csv(data_root / "TESTNEWUSDT_60.csv")
    assert backfill_datasets(dataset_connection, data_root=data_root) == 1


def test_backfill_datasets_skips_while_concurrent_run_holds_lock(dataset_connection, tmp_path: Path):
    catalog_module = pytest.importorskip("lab.store.catalog")
    data_root = tmp_path / "data"
    _csv(data_root / "TESTUSDT_60.csv")
    assert backfill_datasets(dataset_connection, data_root=data_root) == 1

    _csv(data_root / "TESTNEWUSDT_60.csv")
    with catalog_module._BACKFILL_LOCK:
        # Another request is already refreshing the catalog; this one serves
        # the current rows instead of piling into a second write transaction.
        assert backfill_datasets(dataset_connection, data_root=data_root) == 0
    # Once the first run releases the lock, the pending registration completes.
    assert backfill_datasets(dataset_connection, data_root=data_root) == 1
    assert (
        dataset_connection.execute(
            "SELECT COUNT(*) FROM datasets WHERE repo_path LIKE '%TESTNEWUSDT_60.csv'"
        ).fetchone()[0]
        == 1
    )


def test_upsert_dataset_dedupes_alias_paths(dataset_connection, tmp_path: Path):
    data_root = tmp_path / "data"
    _csv(data_root / "TESTUSDT_60.csv")
    assert backfill_datasets(dataset_connection, data_root=data_root) == 1

    # The same file referenced with a messy-but-equivalent path must update the
    # existing row instead of registering a duplicate.
    kept_id = upsert_dataset(
        dataset_connection,
        repo_path=str(data_root / "." / "TESTUSDT_60.csv"),
        source="data_file",
    )
    rows = dataset_connection.execute("SELECT id FROM datasets").fetchall()
    assert len(rows) == 1
    assert kept_id == rows[0]["id"]


def test_backfill_datasets_survives_concurrent_calls(dataset_connection, tmp_path: Path):
    import threading

    data_root = tmp_path / "data"
    _write_sample_csvs(data_root, file_count=20)
    results: list[int] = []
    errors: list[Exception] = []
    start_gate = threading.Event()

    def run_backfill() -> None:
        start_gate.wait()
        connection = open_database(tmp_path / "lab.db")
        try:
            results.append(backfill_datasets(connection, data_root=data_root))
        except Exception as error:  # noqa: BLE001 - the test asserts no sqlite lock errors
            errors.append(error)
        finally:
            connection.close()

    threads = [threading.Thread(target=run_backfill) for _ in range(4)]
    for thread in threads:
        thread.start()
    start_gate.set()
    for thread in threads:
        thread.join()

    assert not errors
    assert dataset_connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 20
