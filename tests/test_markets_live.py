from pathlib import Path

from traderbot.markets.live_visualize import fetch_recent_bars, run_live_market_visualization
from traderbot.markets.registry import DEFAULT_JOBS_PATH, list_supported_markets, market_spec_from_symbol, markets_catalog_dict


def test_market_spec_from_symbol():
    assert market_spec_from_symbol("BTCIRT").label == "BTC/RLS"
    assert market_spec_from_symbol("ETHUSDT").dst == "usdt"


def test_list_supported_markets_from_repo_jobs():
    markets = list_supported_markets()
    symbols = {m.symbol for m in markets}
    assert "BTCIRT" in symbols
    assert "ETHUSDT" in symbols
    assert len(markets) >= 2


def test_markets_catalog_dict_from_jobs():
    out = markets_catalog_dict(DEFAULT_JOBS_PATH)
    symbols = {m["symbol"] for m in out["markets"]}
    assert "BTCIRT" in symbols
    assert out["market_count"] == len(out["markets"])
    assert "jobs_file" in out
    assert "60" in out["udf_resolutions"]


def test_markets_catalog_dict_jobs_file(tmp_path):
    jobs = tmp_path / "jobs.json"
    jobs.write_text('[{"src":"btc","dst":"rls","interval":"60"}]', encoding="utf-8")
    out = markets_catalog_dict(jobs)
    assert out["jobs_file"] == str(jobs)
    assert out["markets"][0]["symbol"] == "BTCIRT"


def test_fetch_recent_bars_trims_open_bar(monkeypatch):
    payload = {
        "s": "ok",
        "t": [1, 2, 3],
        "o": [1, 1, 1],
        "h": [1, 1, 1],
        "l": [1, 1, 1],
        "c": [1, 2, 3],
        "v": [1, 1, 1],
    }

    monkeypatch.setattr(
        "traderbot.markets.live_visualize.fetch_ohlc_page",
        lambda **_k: payload,
    )
    rows = fetch_recent_bars(symbol="BTCIRT", resolution="60", max_bars=10)
    assert len(rows) == 2
    assert rows[-1]["close"] == 2


def test_data_live_json(tmp_path, monkeypatch, capsys):
    from traderbot.markets.live_visualize import LiveMarketSnapshot

    snap = LiveMarketSnapshot(
        market=market_spec_from_symbol("BTCIRT"),
        bars=(
            {
                "symbol": "BTCIRT",
                "resolution": "60",
                "timestamp": 1,
                "close": 100.0,
                "open": 1,
                "high": 1,
                "low": 1,
                "volume": 1,
            },
        ),
        last_close=100.0,
        last_timestamp=1,
    )

    monkeypatch.setattr(
        "traderbot.markets.live_visualize.fetch_all_market_snapshots",
        lambda *a, **k: [snap],
    )
    jobs = tmp_path / "jobs.json"
    jobs.write_text('[{"src":"btc","dst":"rls","interval":"60"}]', encoding="utf-8")
    manifest = run_live_market_visualization(
        resolution="60",
        max_bars=10,
        out_dir=tmp_path / "out",
        jobs_path=jobs,
        show=False,
        poll_sec=0.0,
        max_updates=None,
        json_only=True,
    )
    assert manifest["markets"][0]["symbol"] == "BTCIRT"
    assert manifest["markets"][0]["last_close"] == 100.0


def test_data_live_writes_plot(tmp_path, monkeypatch):
    from traderbot.markets.live_visualize import LiveMarketSnapshot

    snap = LiveMarketSnapshot(
        market=market_spec_from_symbol("BTCIRT"),
        bars=tuple(
            {
                "symbol": "BTCIRT",
                "resolution": "60",
                "timestamp": i,
                "close": float(100 + i),
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "volume": 1.0,
            }
            for i in range(5)
        ),
        last_close=104.0,
        last_timestamp=4,
    )
    monkeypatch.setattr(
        "traderbot.markets.live_visualize.fetch_all_market_snapshots",
        lambda *a, **k: [snap],
    )
    jobs = tmp_path / "jobs.json"
    jobs.write_text('[{"src":"btc","dst":"rls","interval":"60"}]', encoding="utf-8")
    out_dir = tmp_path / "live"
    manifest = run_live_market_visualization(
        resolution="60",
        max_bars=5,
        out_dir=out_dir,
        jobs_path=jobs,
        show=False,
        poll_sec=0.0,
        max_updates=None,
        json_only=False,
    )
    assert Path(manifest["visualization"]).is_file()
