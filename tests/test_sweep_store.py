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
