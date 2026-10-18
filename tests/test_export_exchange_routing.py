from lab.job_resolvers import resolve_export_argv_fields
from lab.store.database import init_database, open_database
from traderbot.data.export import _fetch_job_rows


def test_resolve_export_uses_hyperliquid_for_hyperliquid_catalog(tmp_path):
    connection = open_database(tmp_path / "lab.db")
    init_database(connection)
    connection.execute(
        """
        INSERT INTO market_catalog (symbol, src, dst, label, catalog_scope, updated_at_utc)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("GRIFFAINUSDT", "griffain", "USDT", "GRIFFAIN/USDT", "hyperliquid_all", "2026-01-01T00:00:00Z"),
    )
    connection.commit()
    fields = resolve_export_argv_fields(
        connection,
        {
            "market_symbol": "GRIFFAINUSDT",
            "interval": "1",
            "days": 2,
            "max_bars": 500,
        },
    )
    connection.close()
    assert fields["exchange"] == "hyperliquid"
    assert fields["src"] == "griffain"


def test_fetch_job_rows_hyperliquid_branch(monkeypatch):
    captured: dict = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return [{"symbol": "GRIFFAINUSDT", "resolution": "1", "timestamp": 1, "close": 1.0}]

    monkeypatch.setattr(
        "traderbot.hyperliquid.market_data.fetch_hyperliquid_ohlc_range",
        fake_fetch,
    )
    rows = _fetch_job_rows(
        {
            "symbol": "GRIFFAINUSDT",
            "src": "griffain",
            "interval": "1",
            "exchange": "hyperliquid",
        },
        history_from_unix_seconds=100,
        history_to_unix_seconds=200,
    )
    assert captured["src"] == "griffain"
    assert captured["resolution"] == "1"
    assert len(rows) == 1
