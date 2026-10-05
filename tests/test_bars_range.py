from traderbot.utils.bars import filter_bars_by_unix_range


def _bar(open_unix_seconds: int) -> dict:
    return {
        "timestamp": open_unix_seconds,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 0.0,
    }


def test_filter_bars_by_unix_range_respects_bar_close():
    bar_minutes = 60
    bars = [_bar(0), _bar(3600), _bar(7200)]
    filtered = filter_bars_by_unix_range(
        bars,
        start_unix_seconds=3600,
        end_unix_seconds=7200,
        bar_minutes=bar_minutes,
    )
    assert [bar["timestamp"] for bar in filtered] == [3600]


def test_filter_bars_by_unix_range_empty_bounds_returns_copy():
    bars = [_bar(0)]
    assert filter_bars_by_unix_range(bars, bar_minutes=60) == bars
