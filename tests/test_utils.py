from pathlib import Path

from traderbot.algorithms.utils import price_context_kwargs_from_namespace
from traderbot.ml.utils import horizon_label, price_series_from_bars
from traderbot.utils.bars import load_bars_csv, normalize_bar
from traderbot.utils.equity import buy_hold_value, final_equity_from_curve
from traderbot.utils.series import lookup_value_at_or_before, point_at_or_after


def test_lookup_value_at_or_before():
    series = [(0, 10.0), (10, 20.0), (20, 30.0)]
    assert lookup_value_at_or_before(series, 5) == 10.0
    assert lookup_value_at_or_before(series, 10) == 20.0
    assert lookup_value_at_or_before(series, 25) == 30.0
    assert lookup_value_at_or_before(series, -1) is None


def test_point_at_or_after():
    points = [(5, 1.0, 2.0), (15, 3.0, 4.0)]
    assert point_at_or_after(points, 5) == (5, 1.0, 2.0)
    assert point_at_or_after(points, 10) == (15, 3.0, 4.0)
    assert point_at_or_after(points, 100) is None


def test_buy_hold_value():
    assert buy_hold_value(100.0, 50.0, 75.0) == 150.0
    assert buy_hold_value(100.0, None, 75.0) == 100.0


def test_final_equity_from_curve():
    assert final_equity_from_curve([100.0, 110.0]) == 110.0
    assert final_equity_from_curve([]) == 100.0


def test_horizon_label_and_price_series():
    assert horizon_label(60, 4) == "4h"
    bars = [{"timestamp": 1, "close": 100.0}, {"timestamp": 2, "close": 101.0}]
    assert price_series_from_bars(bars) == [(1, 100.0), (2, 101.0)]


def test_price_context_kwargs_from_namespace():
    class Args:
        context_bars = 3
        buy_min_recent_return = -0.02
        sell_max_recent_return = 0.04
        buy_min_fine_last_5m = -0.01
        sell_max_fine_last_5m = 0.02

    kw = price_context_kwargs_from_namespace(Args())
    assert kw["context_bars"] == 3
    assert kw["buy_min_fine_last_5m"] == -0.01


def test_normalize_bar_and_load_csv(tmp_path: Path):
    csv_path = tmp_path / "x.csv"
    csv_path.write_text(
        "symbol,resolution,timestamp,datetime_utc,open,high,low,close,volume\n"
        "BTC,D,1,,1,2,0.5,1.5,10\n",
        encoding="utf-8",
    )
    bars = load_bars_csv(csv_path)
    assert len(bars) == 1
    assert normalize_bar(bars[0])["close"] == 1.5
