from __future__ import annotations

from pathlib import Path

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.backtesting.engine import BacktestResult
from lab.store.catalog import upsert_dataset
from lab.store.database import init_database, open_database
from lab.store.hooks import record_strategy_backtest
from lab.store.queries import fetch_evaluation_run, list_evaluation_runs


def test_record_and_query_strategy_run(tmp_path: Path):
    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    out_dir = tmp_path / "run_out"
    out_dir.mkdir()
    algorithm = algorithm_for_id("sma_cross", fast=3, slow=9)
    result = BacktestResult(
        initial_cash=10_000.0,
        final_equity=10_500.0,
        trades=[],
        equity_curve=[],
    )
    run_id = record_strategy_backtest(
        algorithm,
        result,
        out_dir=out_dir,
        bars=50,
        summary={"return_pct": 5.0, "strategy_id": "sma_cross"},
        extra={"strategy_id": "sma_cross", "csv": "data/BTCIRT_D.csv"},
        database_path=database_path,
    )
    assert run_id

    connection = open_database(database_path)
    try:
        rows = list_evaluation_runs(connection, strategy_id="sma_cross", symbol="BTCIRT")
        assert len(rows) == 1
        assert rows[0].run_kind == "strategy_backtest"

        fetched = fetch_evaluation_run(connection, run_id)
        assert fetched is not None
        assert fetched.metrics["return_pct"] == 5.0
    finally:
        connection.close()


def test_dataset_label_includes_horizon_and_date_range(tmp_path: Path):
    csv_path = tmp_path / "horizons" / "1h" / "TESTIRT_60.csv"
    csv_path.parent.mkdir(parents=True)
    csv_path.write_text(
        "symbol,resolution,timestamp,datetime_utc,open,high,low,close,volume\n"
        "TESTIRT,60,1700000000,2023-11-14T22:13:20+00:00,1,1,1,1,1\n"
        "TESTIRT,60,1700086400,2023-11-15T22:13:20+00:00,2,2,2,2,1\n",
        encoding="utf-8",
    )
    connection = open_database(tmp_path / "lab.db")
    init_database(connection)
    try:
        dataset_id = upsert_dataset(connection, repo_path=str(csv_path), source="test")
        row = connection.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        assert row["horizon_label"] == "1h"
        assert row["range_start_utc"] == "2023-11-14"
        assert row["range_end_utc"] == "2023-11-15"
        assert row["label"] == "TESTIRT · 60 · horizon 1h · 2023-11-14 to 2023-11-15"
        assert row["symbol"] == "TESTIRT"
        assert row["resolution"] == "60"

        messy = csv_path.parent / ".." / "1h" / csv_path.name
        connection.execute(
            """
            INSERT INTO datasets (
                id, label, symbol, resolution, repo_path, source, registered_at_utc, last_seen_at_utc
            ) VALUES ('legacy', 'old', 'TESTIRT', '60', ?, 'export_job', '2020-01-01T00:00:00+00:00', '2020-01-01T00:00:00+00:00')
            """,
            (messy.as_posix(),),
        )
        kept_id = upsert_dataset(connection, repo_path=str(csv_path), source="data_file")
        rows = connection.execute("SELECT id, repo_path, source, label FROM datasets").fetchall()
        assert len(rows) == 1
        assert kept_id == dataset_id
        assert rows[0]["source"] == "test"
        assert "horizon 1h" in rows[0]["label"]
    finally:
        connection.close()
