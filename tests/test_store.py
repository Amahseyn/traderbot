from __future__ import annotations

from pathlib import Path

import pytest

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.backtesting.engine import BacktestResult
from lab.store.catalog import upsert_dataset
from lab.store.database import init_database, open_database
from lab.store.hooks import record_strategy_backtest
from lab.store.constants import CONFIG_KIND_STRATEGY, RUN_KIND_STRATEGY_BACKTEST
from lab.store.queries import count_evaluation_runs, fetch_dashboard_stats, fetch_evaluation_run, list_evaluation_runs
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

    # Re-run in the same out_dir must update metrics instead of leaving stale records
    run_id2 = record_strategy_backtest(
        algorithm,
        result,
        out_dir=out_dir,
        bars=50,
        summary={"return_pct": 12.0, "strategy_id": "sma_cross"},
        extra={"strategy_id": "sma_cross", "csv": "data/BTCIRT_D.csv"},
        database_path=database_path,
    )
    assert run_id2 == run_id

    connection = open_database(database_path)
    try:
        updated = fetch_evaluation_run(connection, run_id)
        assert updated is not None
        assert updated.metrics["return_pct"] == 12.0
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
    win_rate_pct: float | None = None,
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
    metrics: dict[str, Any] = {"return_pct": return_pct}
    if win_rate_pct is not None:
        metrics["win_rate_pct"] = win_rate_pct
    return insert_evaluation_run(
        connection,
        config_id=config_id,
        run_kind=RUN_KIND_STRATEGY_BACKTEST,
        out_dir=out_dir,
        metrics=metrics,
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
            win_rate_pct=60.0,
        )
        _insert_strategy_run(
            connection,
            out_dir=tmp_path / "eth",
            symbol="ETHIRT",
            resolution="60",
            csv_path="data/ETHIRT_60.csv",
            return_pct=-2.0,
            win_rate_pct=40.0,
        )
        _insert_strategy_run(
            connection,
            out_dir=tmp_path / "btc2",
            symbol="BTCIRT",
            resolution="D",
            csv_path="data/BTCIRT_D.csv",
            return_pct=4.0,
            win_rate_pct=50.0,
        )
        connection.commit()

        stats = fetch_dashboard_stats(connection)
        assert stats["backtest_summary"]["count"] == 3
        assert stats["backtest_summary"]["positive_pct"] == pytest.approx(200 / 3)
        assert stats["backtest_summary"]["avg_win_rate"] == pytest.approx(50.0)
        assert stats["top_markets"][0]["symbol"] == "BTCIRT"
        assert stats["top_markets"][0]["avg_return"] == pytest.approx(7.0)
        assert stats["top_markets"][0]["avg_win_rate"] == pytest.approx(55.0)
        assert stats["top_strategies"][0]["strategy_id"] == "sma_cross"
        assert stats["top_strategies"][0]["avg_win_rate"] == pytest.approx(50.0)
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


def test_list_evaluation_runs_advanced_filters_and_sorting(tmp_path: Path):
    connection = open_database(tmp_path / "lab.db")
    init_database(connection)
    try:
        # Run 1: BTCIRT, resolution=60, sma_cross, return=10.5%, trades=15, optimized
        config1 = upsert_configuration(
            connection,
            config_kind=CONFIG_KIND_STRATEGY,
            strategy_id="sma_cross",
            model_id=None,
            symbol="BTCIRT",
            resolution="60",
            horizon_label=None,
            parameters={"fast": 10, "slow": 30},
            data_context={"csv": "data/BTCIRT_60.csv", "optimizer_enabled": True},
        )
        insert_evaluation_run(
            connection,
            config_id=config1,
            run_kind=RUN_KIND_STRATEGY_BACKTEST,
            out_dir=tmp_path / "run1",
            metrics={"return_pct": 10.5, "trades": 15, "final_equity": 11050.0, "trade_win_rate": 0.7},
        )

        # Run 2: ETHIRT, resolution=15, rsi_threshold, return=-3.2%, trades=5, default
        config2 = upsert_configuration(
            connection,
            config_kind=CONFIG_KIND_STRATEGY,
            strategy_id="rsi_threshold",
            model_id=None,
            symbol="ETHIRT",
            resolution="15",
            horizon_label=None,
            parameters={"period": 14},
            data_context={"csv": "data/ETHIRT_15.csv"},
        )
        insert_evaluation_run(
            connection,
            config_id=config2,
            run_kind=RUN_KIND_STRATEGY_BACKTEST,
            out_dir=tmp_path / "run2",
            metrics={"return_pct": -3.2, "trades": 5, "final_equity": 9680.0, "win_rate_pct": 40.0},
        )

        # Run 3: SOLIRT, resolution=D, sma_cross, return=0.0%, trades=0, default
        config3 = upsert_configuration(
            connection,
            config_kind=CONFIG_KIND_STRATEGY,
            strategy_id="sma_cross",
            model_id=None,
            symbol="SOLIRT",
            resolution="D",
            horizon_label=None,
            parameters={"fast": 5, "slow": 20},
            data_context={"csv": "data/SOLIRT_D.csv"},
        )
        insert_evaluation_run(
            connection,
            config_id=config3,
            run_kind=RUN_KIND_STRATEGY_BACKTEST,
            out_dir=tmp_path / "run3",
            metrics={"return_pct": 0.0, "trades": 0, "final_equity": 10000.0},
        )
        connection.commit()

        # 1. Resolution filter
        assert len(list_evaluation_runs(connection, resolution="60")) == 1
        assert len(list_evaluation_runs(connection, resolution="15")) == 1
        assert len(list_evaluation_runs(connection, resolution="D")) == 1
        assert len(list_evaluation_runs(connection, resolution="5")) == 0

        # 2. Outcome filter
        profitable = list_evaluation_runs(connection, outcome="profitable")
        assert len(profitable) == 1 and profitable[0].symbol == "BTCIRT"
        losses = list_evaluation_runs(connection, outcome="loss")
        assert len(losses) == 1 and losses[0].symbol == "ETHIRT"
        breakeven = list_evaluation_runs(connection, outcome="breakeven")
        assert len(breakeven) == 1 and breakeven[0].symbol == "SOLIRT"
        high = list_evaluation_runs(connection, outcome="high_return")
        assert len(high) == 1 and high[0].symbol == "BTCIRT"

        # 3. Optimizer filter
        opt_runs = list_evaluation_runs(connection, optimizer="optimized")
        assert len(opt_runs) == 1 and opt_runs[0].symbol == "BTCIRT"
        def_runs = list_evaluation_runs(connection, optimizer="default")
        assert len(def_runs) == 2

        # 4. Trades filter
        with_tr = list_evaluation_runs(connection, trades="with_trades")
        assert len(with_tr) == 2
        no_tr = list_evaluation_runs(connection, trades="no_trades")
        assert len(no_tr) == 1 and no_tr[0].symbol == "SOLIRT"

        # 5. Query search
        q_eth = list_evaluation_runs(connection, query="ETH")
        assert len(q_eth) == 1 and q_eth[0].symbol == "ETHIRT"
        q_rsi = list_evaluation_runs(connection, query="rsi")
        assert len(q_rsi) == 1 and q_rsi[0].strategy_id == "rsi_threshold"
        q_param = list_evaluation_runs(connection, query="slow")
        assert len(q_param) == 2

        # 6. Sorting
        by_return_desc = list_evaluation_runs(connection, sort_by="return_desc")
        assert [r.symbol for r in by_return_desc] == ["BTCIRT", "SOLIRT", "ETHIRT"]
        by_return_asc = list_evaluation_runs(connection, sort_by="return_asc")
        assert [r.symbol for r in by_return_asc] == ["ETHIRT", "SOLIRT", "BTCIRT"]
        by_win_rate_desc = list_evaluation_runs(connection, sort_by="win_rate_desc")
        assert [r.symbol for r in by_win_rate_desc] == ["BTCIRT", "ETHIRT", "SOLIRT"]
        by_win_rate_asc = list_evaluation_runs(connection, sort_by="win_rate_asc")
        assert [r.symbol for r in by_win_rate_asc] == ["ETHIRT", "BTCIRT", "SOLIRT"]
        by_trades_desc = list_evaluation_runs(connection, sort_by="trades_desc")
        assert [r.symbol for r in by_trades_desc] == ["BTCIRT", "ETHIRT", "SOLIRT"]
        by_equity_desc = list_evaluation_runs(connection, sort_by="equity_desc")
        assert [r.symbol for r in by_equity_desc] == ["BTCIRT", "SOLIRT", "ETHIRT"]
        by_equity_asc = list_evaluation_runs(connection, sort_by="equity_asc")
        assert [r.symbol for r in by_equity_asc] == ["ETHIRT", "SOLIRT", "BTCIRT"]

        # 7. Count matching
        assert count_evaluation_runs(connection, resolution="60") == 1
        assert count_evaluation_runs(connection, outcome="profitable") == 1
        assert count_evaluation_runs(connection, optimizer="optimized") == 1
        assert count_evaluation_runs(connection, trades="no_trades") == 1
        assert count_evaluation_runs(connection, query="rsi") == 1
    finally:
        connection.close()


def test_runs_win_rate_backfill_and_canonical_parsing(tmp_path: Path):
    from lab.store.canonical import parse_symbol_resolution_from_csv
    from lab.store.database import backfill_runs_win_rate

    # Canonical resolution parsing guards
    assert parse_symbol_resolution_from_csv("data/BTCIRT_60.csv") == ("BTCIRT", "60")
    assert parse_symbol_resolution_from_csv("data/BTCIRT_60_last24h.csv") == ("BTCIRT", "60_last24h")
    assert parse_symbol_resolution_from_csv("nobitex://sma_cross") == (None, None)
    assert parse_symbol_resolution_from_csv("hyperliquid://bollinger_mean_reversion") == (None, None)

    # Backfill verification
    connection = open_database(tmp_path / "lab.db")
    init_database(connection)
    try:
        config_id = upsert_configuration(
            connection,
            config_kind=CONFIG_KIND_STRATEGY,
            strategy_id="sma_cross",
            model_id=None,
            symbol="BTCIRT",
            resolution="60",
            horizon_label=None,
            parameters={"fast": 5, "slow": 20},
            data_context={"csv": "data/BTCIRT_60.csv"},
        )
        logs = [
            {"action": "buy", "price": 100, "cash_before": 1000, "position_after": 1, "equity_after": 1000, "timestamp": 100},
            {"action": "sell", "price": 110, "position_after": 0, "equity_after": 1100, "timestamp": 200},
            {"action": "buy", "price": 110, "cash_before": 1100, "position_after": 1, "equity_after": 1100, "timestamp": 300},
            {"action": "sell", "price": 90, "position_after": 0, "equity_after": 990, "timestamp": 400},
        ]
        run_id = insert_evaluation_run(
            connection,
            config_id=config_id,
            run_kind=RUN_KIND_STRATEGY_BACKTEST,
            out_dir=tmp_path / "run_bf",
            metrics={"trade_logs": logs, "trades": 4, "final_equity": 990, "initial_cash": 1000},
        )
        connection.commit()

        # Before backfill, win_rate_pct in JSON is null
        row_before = fetch_evaluation_run(connection, run_id)
        assert row_before is not None
        assert "win_rate_pct" not in row_before.metrics

        # Run backfill
        updated = backfill_runs_win_rate(connection)
        assert updated == 1

        # After backfill, win_rate_pct is populated (1 win out of 2 trips = 50.0%)
        row_after = fetch_evaluation_run(connection, run_id)
        assert row_after is not None
        assert row_after.metrics.get("win_rate_pct") == 50.0
    finally:
        connection.close()

