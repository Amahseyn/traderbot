from traderbot.data.export import load_jobs, write_csv
from traderbot.markets.market_data import fetch_latest_closed_bar, fetch_one_minute_bars, incremental_bar_source, market_symbol, ohlc_rows
from traderbot.utils.bars import one_minute_history_to_timestamp


def test_market_symbol():
    assert market_symbol("btc", "rls") == "BTCIRT"
    assert market_symbol("eth", "usdt") == "ETHUSDT"


def test_ohlc_rows():
    payload = {
        "s": "ok",
        "t": [100, 200],
        "o": [1, 2],
        "h": [3, 4],
        "l": [0.5, 1.5],
        "c": [2, 3],
        "v": [10, 20],
    }
    rows = ohlc_rows(payload, symbol="BTCIRT", resolution="D")
    assert len(rows) == 2
    assert rows[0]["close"] == 2
    assert rows[1]["timestamp"] == 200


def test_load_jobs(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text(
        '[{"src":"btc","dst":"rls","interval":"D"}]',
        encoding="utf-8",
    )
    jobs = load_jobs(path)
    assert jobs[0]["symbol"] == "BTCIRT"
    assert jobs[0]["interval"] == "D"


def test_write_csv(tmp_path):
    path = tmp_path / "out.csv"
    write_csv(
        path,
        [
            {
                "symbol": "BTCIRT",
                "resolution": "D",
                "timestamp": 1,
                "datetime_utc": "1970-01-01T00:00:01+00:00",
                "open": 1,
                "high": 2,
                "low": 0.5,
                "close": 1.5,
                "volume": 9,
            }
        ],
    )
    text = path.read_text(encoding="utf-8")
    assert "BTCIRT" in text
    assert "close" in text.splitlines()[0]


def test_one_minute_history_to_timestamp_is_one_minute_before_known_at():
    known_at_unix_seconds = 1_700_000_000
    assert one_minute_history_to_timestamp(known_at_unix_seconds) == known_at_unix_seconds - 60


def test_fetch_one_minute_bars_uses_history_to_one_minute_before(monkeypatch):
    known_at_unix_seconds = 1_000
    captured: dict[str, int] = {}

    def fake_page(**kwargs):
        captured["history_to_unix_seconds"] = kwargs["history_to_unix_seconds"]
        return {
            "s": "ok",
            "t": [880, 940, 1000],
            "o": [1, 1, 1],
            "h": [1, 1, 1],
            "l": [1, 1, 1],
            "c": [1, 2, 3],
            "v": [1, 1, 1],
        }

    monkeypatch.setattr("traderbot.markets.market_data.fetch_ohlc_page", fake_page)
    rows = fetch_one_minute_bars(symbol="BTCIRT", known_at_unix_seconds=known_at_unix_seconds, max_bars=10)
    assert captured["history_to_unix_seconds"] == known_at_unix_seconds - 60
    assert [r["timestamp"] for r in rows] == [880, 940]


def test_fetch_latest_closed_bar_known_at(monkeypatch):
    known_at_unix_seconds = 3_700

    def fake_page(**kwargs):
        assert kwargs["history_to_unix_seconds"] == known_at_unix_seconds - 3600
        return {
            "s": "ok",
            "t": [100, 200, 300],
            "o": [1, 1, 1],
            "h": [1, 1, 1],
            "l": [1, 1, 1],
            "c": [1, 2, 3],
            "v": [1, 1, 1],
        }

    monkeypatch.setattr("traderbot.markets.market_data.fetch_ohlc_page", fake_page)
    bar = fetch_latest_closed_bar(symbol="BTCIRT", resolution="60", known_at_unix_seconds=known_at_unix_seconds)
    assert bar is not None
    assert bar["timestamp"] == 200


def test_incremental_bar_source_dedupes(monkeypatch):
    bar_a = {
        "symbol": "BTCIRT",
        "resolution": "60",
        "timestamp": 100,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1.0,
    }
    bar_b = {**bar_a, "timestamp": 200, "close": 2.0}
    queue = [bar_a, bar_a, bar_b, bar_b]

    def fake_fetch(**_kwargs):
        return queue.pop(0) if queue else bar_b

    monkeypatch.setattr("traderbot.markets.market_data.fetch_latest_closed_bar", fake_fetch)
    source = incremental_bar_source(symbol="BTCIRT", resolution="60")
    assert source()["timestamp"] == 100
    assert source() is None
    assert source()["timestamp"] == 200
    assert source() is None
