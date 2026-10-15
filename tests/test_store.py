from __future__ import annotations

from pathlib import Path

import pytest

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.backtesting.engine import BacktestResult
from lab.store.catalog import upsert_dataset
from lab.store.database import init_database, open_database
from lab.store.hooks import record_strategy_backtest
from lab.store.constants import CONFIG_KIND_STRATEGY, RUN_KIND_STRATEGY_BACKTEST
from lab.store.queries import fetch_dashboard_stats, fetch_evaluation_run, list_evaluation_runs
from lab.store.record import insert_evaluation_run, upsert_configuration


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


def _insert_strategy_run(
    connection,
    *,
    out_dir: Path,
    symbol: str,
    resolution: str,
    csv_path: str,
    horizon_label: str | None = None,
    return_pct: float = 1.0,
    strategy_id: str = "sma_cross",
) -> str:
    config_id = upsert_configuration(
        connection,
        config_kind=CONFIG_KIND_STRATEGY,
        strategy_id=strategy_id,
        model_id=None,
        symbol=symbol,
        resolution=resolution,
        horizon_label=horizon_label,
        parameters={"algorithm": strategy_id},
        data_context={"csv": csv_path, "symbol": symbol, "resolution": resolution},
    )
    return insert_evaluation_run(
        connection,
        config_id=config_id,
        run_kind=RUN_KIND_STRATEGY_BACKTEST,
        out_dir=out_dir,
        metrics={"return_pct": return_pct},
    )


def test_fetch_dashboard_stats_aggregates_markets_and_intervals(tmp_path: Path):
    connection = open_database(tmp_path / "lab.db")
    init_database(connection)
    try:
        _insert_strategy_run(
            connection,
            out_dir=tmp_path / "btc",
            symbol="BTCIRT",
            resolution="60",
            csv_path="data/BTCIRT_60.csv",
            return_pct=10.0,
        )
        _insert_strategy_run(
            connection,
            out_dir=tmp_path / "eth",
            symbol="ETHIRT",
            resolution="60",
            csv_path="data/ETHIRT_60.csv",
            return_pct=-2.0,
        )
        _insert_strategy_run(
            connection,
            out_dir=tmp_path / "btc2",
            symbol="BTCIRT",
            resolution="D",
            csv_path="data/BTCIRT_D.csv",
            return_pct=4.0,
        )
        connection.commit()

        stats = fetch_dashboard_stats(connection)
        assert stats["backtest_summary"]["count"] == 3
        assert stats["backtest_summary"]["positive_pct"] == pytest.approx(200 / 3)
        assert stats["top_markets"][0]["symbol"] == "BTCIRT"
        assert stats["top_markets"][0]["avg_return"] == pytest.approx(7.0)
        assert stats["top_strategies"][0]["strategy_id"] == "sma_cross"
        interval_labels = {row["interval_label"] for row in stats["top_intervals"]}
        assert interval_labels == {"60", "D"}
    finally:
        connection.close()


def test_list_runs_horizon_matches_bar_resolution_and_dataset(tmp_path: Path):
    connection = open_database(tmp_path / "lab.db")
    init_database(connection)
    try:
        hour_id = _insert_strategy_run(
            connection,
            out_dir=tmp_path / "hour",
            symbol="BTCIRT",
            resolution="60",
            csv_path="data/BTCIRT_60.csv",
        )
        suffixed_id = _insert_strategy_run(
            connection,
            out_dir=tmp_path / "suffixed",
            symbol="BTCIRT",
            resolution="60_last24h",
            csv_path="data/BTCIRT_60_last24h.csv",
        )
        quarter_id = _insert_strategy_run(
            connection,
            out_dir=tmp_path / "quarter",
            symbol="ETHIRT",
            resolution="15",
            csv_path="data/crypto/horizons/4h/ETHIRT_15.csv",
        )
        connection.commit()

        hour_ids = {row.id for row in list_evaluation_runs(connection, horizon_label="1h")}
        assert hour_ids == {hour_id, suffixed_id}

        quarter_ids = {row.id for row in list_evaluation_runs(connection, horizon_label="15m")}
        assert quarter_ids == {quarter_id}

        ahead_ids = {row.id for row in list_evaluation_runs(connection, horizon_label="4h")}
        assert ahead_ids == {quarter_id}
        assert list_evaluation_runs(connection, horizon_label="1d") == []
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
