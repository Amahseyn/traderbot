from traderbot.backtesting.bar_windows import (
    compare_window_utc_from_unix,
    fit_window_utc_from_bars,
    unix_to_utc_iso,
)


def test_fit_window_excludes_holdout_tail():
    bars = [{"timestamp": i * 3600} for i in range(10)]
    start, end = fit_window_utc_from_bars(bars, bar_minutes=60, holdout_tail_bars=3)
    assert start == unix_to_utc_iso(0)
    assert end == unix_to_utc_iso(6 * 3600 + 3600)


def test_compare_window_from_unix():
    start, end = compare_window_utc_from_unix(1_700_000_000, 1_700_086_400)
    assert start == "2023-11-14T22:13:20Z"
    assert end == "2023-11-15T22:13:20Z"
