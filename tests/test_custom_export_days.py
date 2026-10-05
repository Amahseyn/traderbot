import pytest

from lab.job_resolvers import JobPayloadError, resolve_custom_research_body
from lab.store.database import init_database, open_database


def _connection_with_market(tmp_path):
    connection = open_database(tmp_path / "lab.db")
    init_database(connection)
    connection.execute(
        """
        INSERT INTO market_catalog (symbol, src, dst, label, catalog_scope, updated_at_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("BTCUSDT", "BTC", "USDT", "BTC/USDT", "nobitex_all", "2026-01-01T00:00:00Z"),
    )
    connection.commit()
    return connection


def test_export_days_by_interval_overrides_default(tmp_path):
    connection = _connection_with_market(tmp_path)
    try:
        prepared = resolve_custom_research_body(
            connection,
            {
                "compare_strategies": True,
                "export_market_symbols": ["BTCUSDT"],
                "export_intervals": ["15", "60"],
                "export_days": 30,
                "export_days_by_interval": {"15": 7},
            },
        )
    finally:
        connection.close()
    jobs = {(job["interval"], job["days"]) for job in prepared["export_jobs"]}
    assert jobs == {("15", 7), ("60", 30)}
    assert prepared["export_days_by_interval"] == {"15": 7}


def test_export_days_by_interval_rejects_bad_values(tmp_path):
    connection = _connection_with_market(tmp_path)
    try:
        with pytest.raises(JobPayloadError):
            resolve_custom_research_body(
                connection,
                {
                    "compare_strategies": True,
                    "export_market_symbols": ["BTCUSDT"],
                    "export_intervals": ["60"],
                    "export_days_by_interval": {"60": 0},
                },
            )
        with pytest.raises(JobPayloadError):
            resolve_custom_research_body(
                connection,
                {
                    "compare_strategies": True,
                    "export_market_symbols": ["BTCUSDT"],
                    "export_intervals": ["60"],
                    "export_days_by_interval": {"60": "lots"},
                },
            )
    finally:
        connection.close()


def test_export_steps_sizes_days_and_trims_bars(tmp_path):
    connection = _connection_with_market(tmp_path)
    try:
        prepared = resolve_custom_research_body(
            connection,
            {
                "compare_strategies": True,
                "export_market_symbols": ["BTCUSDT"],
                "export_intervals": ["15", "60"],
                "export_days": 30,
                "export_steps": 500,
            },
        )
    finally:
        connection.close()
    jobs = {job["interval"]: job for job in prepared["export_jobs"]}
    assert jobs["15"]["days"] == 7  # ceil(500 * 15 / 1440) + 1
    assert jobs["60"]["days"] == 22  # ceil(500 * 60 / 1440) + 1
    assert jobs["15"]["max_bars"] == 500
    assert jobs["60"]["max_bars"] == 500


def test_export_steps_per_interval_override_and_days_win(tmp_path):
    connection = _connection_with_market(tmp_path)
    try:
        prepared = resolve_custom_research_body(
            connection,
            {
                "compare_strategies": True,
                "export_market_symbols": ["BTCUSDT"],
                "export_intervals": ["15", "60"],
                "export_days": 30,
                "export_steps": 500,
                "export_steps_by_interval": {"60": 100},
                "export_days_by_interval": {"15": 7},
            },
        )
    finally:
        connection.close()
    jobs = {job["interval"]: job for job in prepared["export_jobs"]}
    assert jobs["15"]["days"] == 7
    assert jobs["15"]["max_bars"] is None
    assert jobs["60"]["days"] == 6  # ceil(100 * 60 / 1440) + 1
    assert jobs["60"]["max_bars"] == 100


def test_export_steps_rejects_bad_values(tmp_path):
    connection = _connection_with_market(tmp_path)
    try:
        with pytest.raises(JobPayloadError):
            resolve_custom_research_body(
                connection,
                {
                    "compare_strategies": True,
                    "export_market_symbols": ["BTCUSDT"],
                    "export_intervals": ["60"],
                    "export_steps": 0,
                },
            )
        with pytest.raises(JobPayloadError):
            resolve_custom_research_body(
                connection,
                {
                    "compare_strategies": True,
                    "export_market_symbols": ["BTCUSDT"],
                    "export_intervals": ["60"],
                    "export_steps_by_interval": {"60": "lots"},
                },
            )
    finally:
        connection.close()
