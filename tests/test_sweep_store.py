from __future__ import annotations

import json
from pathlib import Path

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.backtesting.sweep import SweepOptions, run_strategy_sweep
from lab.store.database import init_database, open_database
from lab.store.hooks import record_sweep_session
from lab.store.queries import fetch_best_sweep, list_sweep_sessions
from lab.store.sync import sync_results_tree


def _write_csv(path: Path, closes: list[float]) -> None:
    path.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    with path.open("a", encoding="utf-8") as handle:
        for index, close in enumerate(closes):
            handle.write(f"{index},{close},{close},{close},{close},1.0\n")


def _sweep_payload(csv_path: Path) -> dict:
    return run_strategy_sweep(
        SweepOptions(
            csv_path=csv_path,
            strategy_id="sma_cross",
            param_grid={"fast": [2, 5], "slow": [10, 20]},
            holdout_tail_bars=10,
        ),
        default_strategy_namespace(),
    )


def _init_db(database_path: Path):
    connection = open_database(database_path)
    init_database(connection)
    connection.close()


def test_fetch_best_sweep_scoped_by_symbol_and_resolution(tmp_path: Path):
    trending = [float(100 + index * 0.5) for index in range(60)]
    oscillating = [float(100 + (5 if index % 10 < 5 else -5)) for index in range(60)]
    csv_60 = tmp_path / "BTC_60.csv"
    csv_240 = tmp_path / "ETH_240.csv"
    _write_csv(csv_60, trending)
    _write_csv(csv_240, oscillating)
    database_path = tmp_path / "lab.db"
    _init_db(database_path)

    grid = {"fast": [3, 8], "slow": [12, 20]}
    record_sweep_session(
        sweep_payload=run_strategy_sweep(
            SweepOptions(csv_path=csv_60, strategy_id="sma_cross", param_grid=grid, holdout_tail_bars=10),
            default_strategy_namespace(),
        ),
        database_path=database_path,
    )
    record_sweep_session(
        sweep_payload=run_strategy_sweep(
            SweepOptions(csv_path=csv_240, strategy_id="sma_cross", param_grid=grid, holdout_tail_bars=10),
            default_strategy_namespace(),
        ),
        database_path=database_path,
    )

    connection = open_database(database_path)
    try:
        btc_60 = fetch_best_sweep(connection, strategy_id="sma_cross", symbol="BTC", resolution="60")
        eth_240 = fetch_best_sweep(connection, strategy_id="sma_cross", symbol="ETH", resolution="240")
        assert btc_60 is not None and eth_240 is not None
        assert btc_60["best_params"] != eth_240["best_params"]
        assert fetch_best_sweep(connection, strategy_id="sma_cross", symbol="BTC", resolution="240") is None
        assert fetch_best_sweep(connection, strategy_id="sma_cross", symbol="ETH", resolution="60") is None
    finally:
        connection.close()


def test_record_and_query_sweep_best(tmp_path: Path):
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, [float(100 + index) for index in range(60)])
    database_path = tmp_path / "lab.db"
    _init_db(database_path)

    payload = _sweep_payload(csv_path)
    session_id = record_sweep_session(
        sweep_payload=payload, manifest_path=None, database_path=database_path
    )
    assert session_id

    connection = open_database(database_path)
    try:
        rows = list_sweep_sessions(connection, strategy_id="sma_cross")
        assert len(rows) == 1
        assert rows[0]["symbol"] == "BTC"
        assert rows[0]["resolution"] == "60"
        assert set(rows[0]["best_params"]) == {"fast", "slow"}
        assert rows[0]["optimize_start_utc"] is not None
        assert rows[0]["optimize_end_utc"] is not None
        assert rows[0]["optimize_end_utc"] > rows[0]["optimize_start_utc"]

        best = fetch_best_sweep(connection, strategy_id="sma_cross", symbol="btc")
        assert best is not None and best["id"] == session_id

        assert fetch_best_sweep(connection, strategy_id="rsi_threshold") is None
    finally:
        connection.close()


def test_sync_indexes_sweep_manifest(tmp_path: Path):
    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, [float(100 + index) for index in range(60)])
    payload = _sweep_payload(csv_path)

    root = tmp_path / "results"
    manifest_dir = root / "sweep" / "BTC_60"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "sweep_manifest.json").write_text(json.dumps(payload), encoding="utf-8")

    database_path = tmp_path / "lab.db"
    _init_db(database_path)
    counts = sync_results_tree(root, database_path=database_path)
    assert counts["sweep"] == 1

    connection = open_database(database_path)
    try:
        best = fetch_best_sweep(connection, strategy_id="sma_cross", symbol="BTC")
        assert best is not None
        assert best["manifest_path"].endswith("sweep_manifest.json")
    finally:
        connection.close()


def test_sweep_api_endpoints(tmp_path: Path):
    import pytest

    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    csv_path = tmp_path / "BTC_60.csv"
    _write_csv(csv_path, [float(100 + index) for index in range(60)])
    database_path = tmp_path / "lab.db"
    _init_db(database_path)
    record_sweep_session(
        sweep_payload=_sweep_payload(csv_path), database_path=database_path
    )

    client = TestClient(create_app(database_path=database_path))
    assert client.get("/api/sweeps/best", params={"strategy_id": "rsi_threshold"}).status_code == 404
    best = client.get(
        "/api/sweeps/best", params={"strategy_id": "sma_cross", "symbol": "BTC"}
    ).json()
    assert set(best["best_params"]) == {"fast", "slow"}
    rows = client.get("/api/sweeps", params={"strategy_id": "sma_cross"}).json()
    assert len(rows) == 1
    assert client.get("/api/stats").json()["sweep_count"] == 1


def test_markets_ohlc_endpoint(tmp_path: Path, monkeypatch):
    import pytest

    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    database_path = tmp_path / "lab.db"
    _init_db(database_path)

    bars = [
        {
            "symbol": "ARBUSDT",
            "resolution": "1",
            "timestamp": 100,
            "open": 1.0,
            "high": 1.1,
            "low": 0.9,
            "close": 1.05,
            "volume": 10.0,
        },
    ]

    monkeypatch.setattr(
        "traderbot.markets.market_data.fetch_recent_closed_bars",
        lambda **_kwargs: bars,
    )

    client = TestClient(create_app(database_path=database_path))
    response = client.get(
        "/api/markets/ohlc",
        params={"src": "arb", "dst": "usdt", "resolution": "1", "max_bars": 50},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "ARBUSDT"
    assert payload["bars"] == bars


def test_strategy_params_endpoint(tmp_path: Path):
    import pytest

    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    database_path = tmp_path / "lab.db"
    _init_db(database_path)

    client = TestClient(create_app(database_path=database_path))
    assert client.get("/api/catalog/strategy-params").status_code in (400, 422)
    assert client.get("/api/catalog/strategy-params", params={"strategy_id": "nope"}).status_code == 404
    payload = client.get(
        "/api/catalog/strategy-params", params={"strategy_id": "rsi_threshold"}
    ).json()
    assert payload["strategy_id"] == "rsi_threshold"
    by_name = {field["name"]: field for field in payload["params"]}
    assert by_name["period"] == {"name": "period", "kind": "int", "default": 14}
    assert by_name["oversold"]["kind"] == "float"
    assert by_name["buy_min_fine_last_5m"] == {
        "name": "buy_min_fine_last_5m",
        "kind": "optional_float",
        "default": None,
    }


def test_resolve_sweep_body_passes_all_namespace_knobs(tmp_path: Path):
    from lab.job_resolvers import resolve_sweep_body
    from lab.store.catalog import upsert_dataset

    csv_path = tmp_path / "BTC_60.csv"
    csv_path.write_text("timestamp,open,high,low,close,volume\n0,1,1,1,1,1\n", encoding="utf-8")
    database_path = tmp_path / "lab.db"
    _init_db(database_path)

    connection = open_database(database_path)
    try:
        upsert_dataset(connection, repo_path=str(csv_path), source="test")
        connection.commit()
        prepared = resolve_sweep_body(
            connection,
            {
                "csv": str(csv_path),
                "strategy_id": "rsi_threshold",
                "mode": "strategies",
                "params": {"period": [7, 14]},
                "buy_min_recent_return": -0.05,
                "price_confirm": True,
            },
        )
    finally:
        connection.close()
    assert prepared["param_grid"] == {"period": [7, 14]}
    assert prepared["buy_min_recent_return"] == -0.05
    assert prepared["price_confirm"] is True


def test_resolve_sweep_body_uses_builtin_grid_when_params_omitted(tmp_path: Path):
    from lab.job_resolvers import resolve_sweep_body
    from lab.store.catalog import upsert_dataset

    csv_path = tmp_path / "BTC_60.csv"
    csv_path.write_text("timestamp,open,high,low,close,volume\n0,1,1,1,1,1\n", encoding="utf-8")
    database_path = tmp_path / "lab.db"
    _init_db(database_path)

    connection = open_database(database_path)
    try:
        upsert_dataset(connection, repo_path=str(csv_path), source="test")
        connection.commit()
        prepared = resolve_sweep_body(
            connection,
            {
                "csv": str(csv_path),
                "strategy_id": "sma_cross",
                "mode": "strategies",
            },
        )
    finally:
        connection.close()
    assert "fast" in prepared["param_grid"]
    assert "slow" in prepared["param_grid"]
    assert prepared["optimize_selection_mode"] == "validation"


def test_resolve_sweep_body_rejects_invalid_selection_mode(tmp_path: Path):
    import pytest

    from lab.job_resolvers import JobPayloadError, resolve_sweep_body
    from lab.store.catalog import upsert_dataset

    csv_path = tmp_path / "BTC_60.csv"
    csv_path.write_text("timestamp,open,high,low,close,volume\n0,1,1,1,1,1\n", encoding="utf-8")
    database_path = tmp_path / "lab.db"
    _init_db(database_path)

    connection = open_database(database_path)
    try:
        upsert_dataset(connection, repo_path=str(csv_path), source="test")
        connection.commit()
        with pytest.raises(JobPayloadError, match="optimize_selection_mode"):
            resolve_sweep_body(
                connection,
                {
                    "csv": str(csv_path),
                    "strategy_id": "sma_cross",
                    "mode": "strategies",
                    "optimize_selection_mode": "bayesian",
                },
            )
    finally:
        connection.close()


def test_fetch_best_sweep_scoped_by_horizon_folder(tmp_path: Path):
    horizon_12h = tmp_path / "data" / "crypto" / "horizons" / "12h"
    horizon_1d = tmp_path / "data" / "crypto" / "horizons" / "1d"
    horizon_12h.mkdir(parents=True)
    horizon_1d.mkdir(parents=True)
    csv_12h = horizon_12h / "ETH_720.csv"
    csv_1d = horizon_1d / "ETH_720.csv"
    _write_csv(csv_12h, [float(100 + index * 0.5) for index in range(60)])
    _write_csv(csv_1d, [float(100 + (5 if index % 10 < 5 else -5)) for index in range(60)])
    database_path = tmp_path / "lab.db"
    _init_db(database_path)

    record_sweep_session(sweep_payload=_sweep_payload(csv_12h), database_path=database_path)
    record_sweep_session(sweep_payload=_sweep_payload(csv_1d), database_path=database_path)

    connection = open_database(database_path)
    try:
        rows = list_sweep_sessions(connection, strategy_id="sma_cross")
        assert sorted(row["horizon_label"] for row in rows) == ["12h", "1d"]
        best_12h = fetch_best_sweep(
            connection, strategy_id="sma_cross", symbol="ETH", resolution="720", horizon_label="12h"
        )
        best_1d = fetch_best_sweep(
            connection, strategy_id="sma_cross", symbol="ETH", resolution="720", horizon_label="1d"
        )
        assert best_12h is not None and best_1d is not None
        assert "horizons/12h/" in best_12h["csv_path"]
        assert "horizons/1d/" in best_1d["csv_path"]
    finally:
        connection.close()


def test_migration_backfills_sweep_horizon_labels(tmp_path: Path):
    from lab.store.schema import SCHEMA_VERSION

    database_path = tmp_path / "lab.db"
    _init_db(database_path)
    legacy_csv = tmp_path / "data" / "crypto" / "horizons" / "12h" / "BTC_60.csv"
    legacy_csv.parent.mkdir(parents=True)
    _write_csv(legacy_csv, [float(100 + index) for index in range(60)])

    connection = open_database(database_path)
    try:
        connection.execute(
            """
            INSERT INTO sweep_sessions (
                id, strategy_id, symbol, resolution, csv_path, rank_by, param_grid_json,
                best_params_json, best_metrics_json, created_at_utc, horizon_label
            ) VALUES ('legacy', 'sma_cross', 'BTC', '60', ?, 'return_pct', '{}', '{}', '{}',
                      '2026-01-01T00:00:00Z', NULL)
            """,
            (str(legacy_csv),),
        )
        connection.execute("UPDATE schema_meta SET value = '7' WHERE key = 'schema_version'")
        connection.commit()
    finally:
        connection.close()

    connection = open_database(database_path)
    try:
        row = connection.execute(
            "SELECT horizon_label FROM sweep_sessions WHERE id = 'legacy'"
        ).fetchone()
        assert row["horizon_label"] == "12h"
        version = connection.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        assert version["value"] == str(SCHEMA_VERSION)
    finally:
        connection.close()
