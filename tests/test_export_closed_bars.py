from traderbot.data.export import run_export


def _row(open_unix_seconds: int) -> dict:
    return {
        "symbol": "BTCIRT",
        "resolution": "60",
        "timestamp": open_unix_seconds,
        "datetime_utc": "",
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 0.0,
    }


def test_run_export_drops_still_open_last_bar(tmp_path, monkeypatch):
    closed_bar = _row(0)
    forming_bar = _row(3600)  # closes at 7200, after to_ts
    monkeypatch.setattr(
        "traderbot.data.export.fetch_ohlc_range",
        lambda **kwargs: [closed_bar, forming_bar],
    )
    jobs = [{"symbol": "BTCIRT", "interval": "60", "days": 1}]
    (paths) = run_export(
        jobs,
        days=1,
        output_dir=tmp_path,
        from_ts=0,
        to_ts=3700,
    )
    assert len(paths) == 1
    lines = paths[0].read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2  # header + closed bar only
    assert lines[1].split(",")[2] == "0"
