"""Hyperliquid live bars: websocket stream, REST fallback, missed-bar replay (no network)."""

from traderbot.hyperliquid import market_data as md
from traderbot.hyperliquid.ws_candles import HyperliquidCandleStream


def _candle(t_ms, c=1.0):
    return {"t": t_ms, "T": t_ms + 59_999, "s": "BTC", "i": "1m", "o": c, "h": c, "l": c, "c": c, "v": 1.0}


def _stream(clock):
    class FakeInfo:
        def subscribe(self, sub, cb):
            self.sub = sub
            return 1

    return HyperliquidCandleStream(
        coin="BTC",
        interval="1m",
        bar_seconds=60,
        normalize=lambda c: md._normalize_candle(c, coin="BTC", resolution="1"),
        info_factory=FakeInfo,
        clock=lambda: clock["now"],
    )


def test_stream_closes_candle_on_next_open_or_elapsed_time():
    clock = {"now": 120.0}
    stream = _stream(clock)
    assert stream.start() and stream.healthy()
    stream.on_message({"channel": "candle", "data": _candle(60_000, 1.0)})
    stream.on_message({"channel": "candle", "data": _candle(60_000, 2.0)})
    stream.on_message({"channel": "candle", "data": _candle(120_000, 3.0)})
    closed = stream.drain_closed()
    assert [(b["timestamp"], b["close"]) for b in closed] == [(60, 2.0)]
    clock["now"] = 181.0  # quiet market: forming 120 candle has closed by time
    assert [b["timestamp"] for b in stream.drain_closed()] == [120]
    clock["now"] = 400.0
    assert not stream.healthy()  # stale -> REST fallback


def test_source_uses_stream_then_falls_back_to_rest_and_replays_gaps(monkeypatch):
    clock = {"now": 120.0}
    stream = _stream(clock)
    stream.start()
    rest_calls = []

    def fake_after(*, src, resolution, after_open_unix_seconds):
        rest_calls.append(after_open_unix_seconds)
        return [md._normalize_candle(_candle(t * 1000), coin="BTC", resolution="1") for t in (120, 180, 240)
                if t > after_open_unix_seconds]

    monkeypatch.setattr(md, "fetch_hyperliquid_closed_bars_after", fake_after)
    source = md.hyperliquid_incremental_bar_source(src="btc", resolution="1", last_bar_open_unix_seconds=0,
                                                   stream=stream)
    stream.on_message({"data": _candle(60_000)})
    stream.on_message({"data": _candle(120_000)})
    assert source()["timestamp"] == 60 and rest_calls == []
    clock["now"] = 1000.0  # websocket went quiet -> REST returns every missed bar in order
    assert source()["timestamp"] == 120
    assert source.pending() == 2
    assert [source()["timestamp"], source()["timestamp"]] == [180, 240]
    assert rest_calls == [60]


def test_hyperliquid_recent_bars_keep_last_closed_candle(monkeypatch):
    now_ms = 10 * 60_000 + 5_000
    monkeypatch.setattr(md.time, "time", lambda: now_ms / 1000)

    class FakeInfo:
        def candles_snapshot(self, coin, interval, start, end):
            return [_candle(t * 60_000) for t in (7, 8, 9, 10)]  # 10 is forming

    monkeypatch.setattr(md, "hyperliquid_info", lambda: FakeInfo())
    bars = md.fetch_hyperliquid_recent_closed_bars(src="btc", resolution="1", max_bars=5)
    assert [b["timestamp"] for b in bars] == [420, 480, 540]
