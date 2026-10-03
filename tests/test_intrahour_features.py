import pytest

from traderbot.data.intrahour import (
    attach_intrahour_to_bars,
    intrahour_features_for_coarse_bars,
    load_one_minute_bars,
    one_minute_csv_for_coarse,
)
from traderbot.data.export import write_csv
from traderbot.ml.dataset import build_supervised
from traderbot.ml.features import build_feature_rows


def _fine_bar(ts: int, close: float) -> dict:
    return {
        "timestamp": ts,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }


def _coarse_bar(ts: int, open_: float, close: float) -> dict:
    return {
        "timestamp": ts,
        "open": open_,
        "high": max(open_, close),
        "low": min(open_, close),
        "close": close,
        "volume": 10.0,
    }


def test_intrahour_features_on_1h_and_5m_coarse():
    t0 = 1_700_000_000
    coarse_1h = [_coarse_bar(t0, 100.0, 110.0)]
    fine_1h = [_fine_bar(t0 + i * 60, 100.0 + i) for i in range(60)]
    feats_1h = intrahour_features_for_coarse_bars(coarse_1h, fine_1h, coarse_minutes=60)[0]
    assert feats_1h["fine_return_in_bar"] == pytest.approx(0.59)
    assert feats_1h["fine_return_last_5m"] == pytest.approx(159.0 / 155.0 - 1.0)

    coarse_5m = [_coarse_bar(t0, 200.0, 210.0)]
    fine_5m = [_fine_bar(t0 + i * 60, 200.0 + 2 * i) for i in range(5)]
    feats_5m = intrahour_features_for_coarse_bars(coarse_5m, fine_5m, coarse_minutes=5)[0]
    assert feats_5m["fine_return_in_bar"] == pytest.approx(0.04)
    assert feats_5m["fine_return_last_5m"] == pytest.approx(0.04)


def test_intrahour_features_causal_wrt_future_fine_bars():
    t0 = 1_700_000_000
    coarse = [_coarse_bar(t0, 100.0, 100.0), _coarse_bar(t0 + 3600, 100.0, 100.0)]
    fine_a = [_fine_bar(t0 + i * 60, 100.0) for i in range(60)]
    fine_b = list(fine_a)
    fine_b.extend(_fine_bar(t0 + 3600 + i * 60, 500.0) for i in range(60))

    fa = intrahour_features_for_coarse_bars(coarse, fine_a, coarse_minutes=60)[0]
    fb = intrahour_features_for_coarse_bars(coarse, fine_b, coarse_minutes=60)[0]
    assert fa == fb


def test_build_supervised_includes_intrahour_columns():
    t0 = 1_700_000_000
    coarse = [_coarse_bar(t0 + i * 3600, 100.0, 100.0 + i) for i in range(80)]
    fine: list[dict] = []
    for h in range(80):
        base = 100.0 + h
        fine.extend(_fine_bar(t0 + h * 3600 + m * 60, base + m * 0.01) for m in range(60))
    xs, ys, _ts, cols, _ends = build_supervised(
        coarse,
        horizon_bars=4,
        bar_minutes=60,
        one_minute_bars=fine,
    )
    assert "fine_return_in_bar" in cols
    assert xs


def test_attach_enriches_bar_dict():
    t0 = 1_700_000_000
    coarse = [_coarse_bar(t0, 50.0, 55.0)]
    fine = [_fine_bar(t0, 50.0), _fine_bar(t0 + 60, 55.0)]
    out = attach_intrahour_to_bars(coarse, fine, coarse_minutes=60)
    assert "fine_return_in_bar" in out[0]


def test_load_one_minute_bars_known_at_trims_future_minutes(tmp_path):
    t0 = 1_700_000_000
    coarse = tmp_path / "BTCIRT_60.csv"
    fine = tmp_path / "BTCIRT_1.csv"
    coarse.write_text("timestamp,open,high,low,close,volume\n", encoding="utf-8")
    write_csv(
        fine,
        [
            _fine_bar(t0, 1.0),
            _fine_bar(t0 + 60, 2.0),
            _fine_bar(t0 + 120, 3.0),
        ],
    )
    known_at_unix_seconds = t0 + 120
    bars = load_one_minute_bars(coarse, known_at_unix_seconds=known_at_unix_seconds)
    assert bars is not None
    assert [int(b["timestamp"]) for b in bars] == [t0, t0 + 60]


def test_one_minute_csv_for_coarse_sibling(tmp_path):
    coarse = tmp_path / "BTCIRT_60.csv"
    fine = tmp_path / "BTCIRT_1.csv"
    coarse.write_text("x", encoding="utf-8")
    fine.write_text("y", encoding="utf-8")
    assert one_minute_csv_for_coarse(coarse) == fine
    assert one_minute_csv_for_coarse(tmp_path / "BTCIRT_240.csv") == fine


def test_build_feature_rows_from_enriched_bars_without_fine_series():
    bar = {
        "timestamp": 1,
        "open": 1.0,
        "high": 1.0,
        "low": 1.0,
        "close": 1.0,
        "volume": 1.0,
        "fine_return_last_5m": 0.02,
    }
    rows = build_feature_rows([bar])
    assert rows[0]["fine_return_last_5m"] == pytest.approx(0.02)
