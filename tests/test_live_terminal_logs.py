from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lab.live_log import assert_log_contains_strategy, parse_json_log_lines, summarize_live_job_log
from lab.live_run_plan import build_live_run_combos
from lab.store.constants import JOB_STATUS_COMPLETED
from lab.store.database import init_database, open_database


class SyncThread:
    def __init__(self, target=None, args=(), kwargs=None, daemon=None):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


def test_concurrent_inprocess_jobs_isolated_stdout(tmp_path: Path):
    import threading

    from lab.jobs import _run_inprocess_job
    from lab.store.constants import JOB_STATUS_COMPLETED

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    for job_id, marker in (("job_a", "JOB_A_ONLY"), ("job_b", "JOB_B_ONLY")):
        connection.execute(
            """
            INSERT INTO jobs (id, job_type, status, payload_json, log_text, created_at_utc)
            VALUES (?, 'terminal-once', 'queued', '{}', '', '2020-01-01T00:00:00+00:00')
            """,
            (job_id,),
        )
    connection.commit()
    connection.close()

    barrier = threading.Barrier(2)

    def connection_factory():
        return open_database(database_path)

    def runner_for(marker: str):
        def runner() -> None:
            barrier.wait()
            for _ in range(200):
                print(marker)
        return runner

    threads = [
        threading.Thread(
            target=_run_inprocess_job,
            args=(connection_factory, job_id, "isolation", runner_for(marker)),
            daemon=True,
        )
        for job_id, marker in (("job_a", "JOB_A_ONLY"), ("job_b", "JOB_B_ONLY"))
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    connection = open_database(database_path)
    rows = {
        row["id"]: row
        for row in connection.execute("SELECT id, log_text, status FROM jobs").fetchall()
    }
    connection.close()
    assert rows["job_a"]["status"] == JOB_STATUS_COMPLETED
    assert rows["job_b"]["status"] == JOB_STATUS_COMPLETED
    assert rows["job_a"]["log_text"].count("JOB_A_ONLY") == 200
    assert "JOB_B_ONLY" not in rows["job_a"]["log_text"]
    assert rows["job_b"]["log_text"].count("JOB_B_ONLY") == 200
    assert "JOB_A_ONLY" not in rows["job_b"]["log_text"]


def _hyperliquid_bar(timestamp: int = 1_700_000_000) -> dict:
    return {
        "symbol": "BTCUSDT",
        "resolution": "60",
        "timestamp": timestamp,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 10.0,
    }


def test_terminal_once_job_log_contains_strategy_from_run(tmp_path: Path, monkeypatch):
    bar = _hyperliquid_bar()

    monkeypatch.setattr(
        "traderbot.terminal.once.fetch_live_recent_closed_bars",
        lambda **_k: [bar],
    )
    monkeypatch.setattr(
        "traderbot.terminal.once.fetch_latest_closed_bar",
        lambda **_k: bar,
    )

    from lab.jobs import _run_inprocess_job
    from lab.terminal_tasks import run_terminal_once_task

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    job_id = "liveonce1"
    payload = {
        "strategy": "bollinger_mean_reversion",
        "src": "btc",
        "dst": "usdt",
        "interval": "60",
        "market_symbol": "BTCUSDT",
        "exchange": "hyperliquid",
    }
    connection.execute(
        """
        INSERT INTO jobs (id, job_type, status, payload_json, log_text, created_at_utc)
        VALUES (?, 'terminal-once', 'queued', ?, '', '2020-01-01T00:00:00+00:00')
        """,
        (job_id, json.dumps(payload)),
    )
    connection.commit()
    connection.close()

    def connection_factory():
        return open_database(database_path)

    _run_inprocess_job(
        connection_factory,
        job_id,
        "terminal-once",
        lambda: run_terminal_once_task({**payload, "job_id": job_id}),
    )

    connection = open_database(database_path)
    row = connection.execute("SELECT status, log_text FROM jobs WHERE id = ?", (job_id,)).fetchone()
    connection.close()
    assert row["status"] == JOB_STATUS_COMPLETED
    log_text = row["log_text"]
    assert "task: terminal-once" in log_text
    assert_log_contains_strategy(log_text, "bollinger_mean_reversion")
    once_rows = [r for r in parse_json_log_lines(log_text) if r.get("event") == "once"]
    assert len(once_rows) == 1
    assert once_rows[0]["strategy_id"] == "bollinger_mean_reversion"
    assert once_rows[0]["exchange"] == "hyperliquid"


def test_api_multi_strategy_jobs_distinct_logs(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    bar = _hyperliquid_bar()

    monkeypatch.setattr(
        "traderbot.terminal.once.fetch_live_recent_closed_bars",
        lambda **_k: [bar],
    )
    monkeypatch.setattr(
        "traderbot.terminal.once.fetch_latest_closed_bar",
        lambda **_k: bar,
    )

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    job_ids: list[str] = []

    with patch("lab.jobs.threading.Thread", SyncThread):
        for strategy in ("sma_cross", "rsi_threshold"):
            response = client.post(
                "/api/jobs/terminal-once",
                json={
                    "strategy": strategy,
                    "src": "btc",
                    "dst": "usdt",
                    "interval": "60",
                    "market_symbol": "BTCUSDT",
                    "exchange": "hyperliquid",
                },
            )
            assert response.status_code == 200
            job_ids.append(response.json()["id"])

    logs_by_strategy: dict[str, str] = {}
    for job_id in job_ids:
        detail = client.get(f"/api/jobs/{job_id}").json()
        assert detail["status"] == JOB_STATUS_COMPLETED
        summary = summarize_live_job_log(detail["log_text"])
        assert len(summary["strategy_ids"]) == 1
        logs_by_strategy[summary["strategy_ids"][0]] = detail["log_text"]

    assert set(logs_by_strategy) == {"sma_cross", "rsi_threshold"}
    for sid, log_text in logs_by_strategy.items():
        assert_log_contains_strategy(log_text, sid)


def test_terminal_live_job_log_contains_strategy_banner(tmp_path: Path, monkeypatch):
    bar = _hyperliquid_bar()

    monkeypatch.setattr("lab.terminal_tasks.run_live", lambda _args: None)

    from lab.jobs import _run_inprocess_job
    from lab.terminal_tasks import run_terminal_live_task

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    job_id = "livelive1"
    payload = {
        "strategy": "macd_signal",
        "src": "btc",
        "dst": "usdt",
        "interval": "5",
        "market_symbol": "BTCUSDT",
        "exchange": "hyperliquid",
        "max_steps": 1,
    }
    connection.execute(
        """
        INSERT INTO jobs (id, job_type, status, payload_json, log_text, created_at_utc)
        VALUES (?, 'terminal-live', 'queued', ?, '', '2020-01-01T00:00:00+00:00')
        """,
        (job_id, json.dumps(payload)),
    )
    connection.commit()
    connection.close()

    def connection_factory():
        return open_database(database_path)

    _run_inprocess_job(
        connection_factory,
        job_id,
        "terminal-live",
        lambda: run_terminal_live_task({**payload, "job_id": job_id}),
    )

    connection = open_database(database_path)
    row = connection.execute("SELECT status, log_text FROM jobs WHERE id = ?", (job_id,)).fetchone()
    connection.close()
    assert row["status"] == JOB_STATUS_COMPLETED
    summary = summarize_live_job_log(row["log_text"])
    assert summary["terminal_banner"] is not None
    assert summary["terminal_banner"]["strategy"] == "macd_signal"
    assert summary["terminal_banner"]["interval"] == "5"
    assert "task: terminal-live" in row["log_text"]


def test_api_full_cartesian_market_horizon_strategy(tmp_path: Path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from lab.app import create_app

    bar = _hyperliquid_bar()

    monkeypatch.setattr(
        "traderbot.terminal.once.fetch_live_recent_closed_bars",
        lambda **_k: [bar],
    )
    monkeypatch.setattr(
        "traderbot.terminal.once.fetch_latest_closed_bar",
        lambda **_k: bar,
    )

    combos = build_live_run_combos(
        multi_run=True,
        src="btc",
        dst="usdt",
        market_symbol="BTCUSDT",
        batch_markets=[
            {"src": "btc", "dst": "usdt", "symbol": "BTCUSDT"},
            {"src": "eth", "dst": "usdt", "symbol": "ETHUSDT"},
        ],
        horizons=["1", "60"],
        multi_strategy=True,
        strategy_id="sma_cross",
        batch_strategy_ids=["sma_cross", "rsi_threshold"],
    )
    assert len(combos) == 8

    database_path = tmp_path / "lab.db"
    connection = open_database(database_path)
    init_database(connection)
    connection.close()

    client = TestClient(create_app(database_path=database_path))
    payloads_seen: list[tuple[str, str, str]] = []

    with patch("lab.jobs.threading.Thread", SyncThread):
        for combo in combos:
            response = client.post(
                "/api/jobs/terminal-once",
                json={
                    "strategy": combo.strategy_id,
                    "src": combo.src,
                    "dst": combo.dst,
                    "interval": combo.interval,
                    "market_symbol": combo.symbol,
                    "exchange": "hyperliquid",
                },
            )
            assert response.status_code == 200
            job_id = response.json()["id"]
            job = client.get(f"/api/jobs/{job_id}").json()
            assert job["status"] == JOB_STATUS_COMPLETED
            payload = job["payload"]
            assert payload["strategy"] == combo.strategy_id
            assert payload["interval"] == combo.interval
            assert payload["market_symbol"] == combo.symbol
            assert payload["src"] == combo.src
            assert payload["dst"] == combo.dst
            assert_log_contains_strategy(job["log_text"], combo.strategy_id)
            payloads_seen.append((combo.symbol, combo.interval, combo.strategy_id))

    assert len(set(payloads_seen)) == 8
