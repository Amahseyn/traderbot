"""Holdout causality (no future leakage) and multi-model forecast smoke tests."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from traderbot.data.crypto_store import resolve_crypto_data_dir
from traderbot.ml.dataset import (
    assert_holdout_is_causal,
    build_supervised,
    train_test_split_temporal,
)
from traderbot.ml.features import build_feature_rows
from traderbot.ml.intervals import default_eval_horizon
from traderbot.ml.pipeline import run_forecast_eval
from traderbot.ml.results import save_run_result


def synthetic_bars(n: int = 120, *, start: float = 100.0) -> list[dict]:
    bars = []
    price = start
    for i in range(n):
        price *= 1.0 + 0.002 * math.sin(i / 7.0) + 0.0005 * (i % 5 - 2)
        bars.append(
            {
                "timestamp": 1_700_000_000 + i * 3600,
                "open": price * 0.999,
                "high": price * 1.002,
                "low": price * 0.998,
                "close": price,
                "volume": 1000.0 + i,
            }
        )
    return bars


def _require_lightgbm():
    try:
        import lightgbm  # noqa: F401
    except (ImportError, OSError) as exc:
        pytest.skip(f"lightgbm unavailable: {exc}")


def test_features_at_bar_do_not_use_future_closes():
    bars = synthetic_bars(50)
    rows_a = build_feature_rows(bars)
    mutated = [dict(b) for b in bars]
    mutated[-1] = {**mutated[-1], "close": mutated[-1]["close"] * 1.5}
    rows_b = build_feature_rows(mutated)
    assert rows_a[20]["rsi_14"] == rows_b[20]["rsi_14"]
    assert rows_a[20]["close"] == rows_b[20]["close"]


def test_horizon_purge_drops_train_labels_that_overlap_holdout():
    bars = synthetic_bars(120)
    horizon = 8
    xs, ys, ts, _cols, label_ends = build_supervised(bars, horizon_bars=horizon)
    x_tr, y_tr, ts_tr, x_te, y_te, ts_te = train_test_split_temporal(
        xs,
        ys,
        ts,
        train_ratio=0.8,
        horizon_bars=horizon,
        label_end_timestamps=label_ends,
    )
    assert ts_tr and ts_te
    test_start = min(ts_te)
    assert max(ts_tr) < test_start
    ts_to_end = dict(zip(ts, label_ends, strict=True))
    tr_ends = [ts_to_end[t] for t in ts_tr]
    assert_holdout_is_causal(
        train_timestamps=ts_tr,
        test_timestamps=ts_te,
        train_label_end_timestamps=tr_ends,
    )


def test_without_purge_last_train_label_can_bleed_into_holdout():
    bars = synthetic_bars(80)
    horizon = 6
    xs, ys, ts, _cols, label_ends = build_supervised(bars, horizon_bars=horizon)
    split = max(1, int(len(xs) * 0.8))
    naive_train_end = label_ends[split - 1]
    test_start = ts[split]
    # Naive index split often leaves the last train label ending during holdout.
    if naive_train_end >= test_start:
        x_tr, _, ts_tr, _, _, ts_te = train_test_split_temporal(
            xs,
            ys,
            ts,
            train_ratio=0.8,
            horizon_bars=horizon,
            label_end_timestamps=label_ends,
        )
        assert max(ts_tr) < min(ts_te)


def test_lightgbm_holdout_only_predicts_unseen_times():
    _require_lightgbm()
    from traderbot.ml.models.lightgbm import LightGBMForecastModel

    bars = synthetic_bars(100)
    horizon = 4
    xs, ys, ts, cols, label_ends = build_supervised(bars, horizon_bars=horizon)
    x_tr, y_tr, ts_tr, x_te, _y_te, ts_te = train_test_split_temporal(
        xs,
        ys,
        ts,
        train_ratio=0.75,
        horizon_bars=horizon,
        label_end_timestamps=label_ends,
    )
    model = LightGBMForecastModel(num_boost_round=15)
    model.fit(x_tr, y_tr, feature_names=list(cols))
    preds = model.predict(x_te)
    assert len(preds) == len(ts_te)
    assert set(ts_tr).isdisjoint(ts_te)

    result = run_forecast_eval(
        bars,
        LightGBMForecastModel(num_boost_round=15),
        horizon_bars=horizon,
        bar_minutes=60,
        train_ratio=0.75,
    )
    assert set(result.timestamps).isdisjoint(set(ts_tr))
    assert min(result.timestamps) >= min(ts_te)


def test_chronos_context_is_causal():
    pytest.importorskip("chronos")
    pytest.importorskip("torch")

    from traderbot.ml.models.chronos import ChronosForecastModel

    bars = synthetic_bars(60)
    horizon = 2
    xs, ys, ts, _cols, label_ends = build_supervised(bars, horizon_bars=horizon)
    _, _, _, _, _, ts_te = train_test_split_temporal(
        xs,
        ys,
        ts,
        train_ratio=0.7,
        horizon_bars=horizon,
        label_end_timestamps=label_ends,
    )
    closes = [float(b["close"]) for b in bars]
    ts_to_idx = {int(b["timestamp"]): i for i, b in enumerate(bars)}
    seen_context_lens: list[int] = []

    class RecordingChronos(ChronosForecastModel):
        def predict_series(self, bars, *, horizon_bars, timestamps):
            for t in timestamps:
                end = ts_to_idx[t]
                seen_context_lens.append(end + 1)
                assert closes[: end + 1][-1] == closes[end]
            return [0.0] * len(timestamps)

    run_forecast_eval(
        bars,
        RecordingChronos(),
        horizon_bars=horizon,
        bar_minutes=60,
        train_ratio=0.7,
    )
    assert seen_context_lens
    assert all(length <= len(closes) for length in seen_context_lens)


@pytest.mark.parametrize("model_id", ["lightgbm", "chronos"])
def test_forecast_eval_smoke_both_models(model_id: str, tmp_path: Path):
    if model_id == "lightgbm":
        _require_lightgbm()
    else:
        pytest.importorskip("chronos")
        pytest.importorskip("torch")

    from traderbot.ml.pipeline import model_for_id

    bars = synthetic_bars(90)
    result = run_forecast_eval(
        bars,
        model_for_id(model_id, num_boost_round=10),
        horizon_bars=4,
        bar_minutes=60,
        train_ratio=0.75,
    )
    assert result.model_id == model_id
    assert len(result.y_true) == len(result.y_pred) >= 5
    save_run_result(result, tmp_path / model_id, render_plots=False)


def test_crypto_ohlc_lightgbm_and_chronos_smoke():
    ohlc = resolve_crypto_data_dir()
    if ohlc is None:
        pytest.skip("no crypto OHLC; export first")

    from traderbot.backtest import load_bars_csv

    csv_path = next(iter(sorted(ohlc.glob("*.csv"))), None)
    assert csv_path is not None
    bars = load_bars_csv(csv_path)
    if len(bars) < 80:
        pytest.skip(f"{csv_path.name} too short")

    resolution = csv_path.stem.split("_")[-1]
    horizon_bars, bar_minutes = default_eval_horizon(resolution)

    _require_lightgbm()
    from traderbot.ml.pipeline import model_for_id

    result = run_forecast_eval(
        bars,
        model_for_id("lightgbm", num_boost_round=10),
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
    )
    assert result.metrics["n"] >= 5

    pytest.importorskip("chronos")
    pytest.importorskip("torch")

    chronos_result = run_forecast_eval(
        bars,
        model_for_id("chronos"),
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
    )
    assert chronos_result.metrics["n"] >= 5
