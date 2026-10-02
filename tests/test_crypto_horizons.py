"""Crypto data layout: OHLC + per-horizon complete tail slices."""

from __future__ import annotations

import json
from pathlib import Path

from traderbot.backtest import load_bars_csv
from traderbot.data.crypto_store import (
    build_horizon_datasets,
    is_contiguous_tail,
    materialize_crypto_tree,
    recommended_tail_bars,
)
from traderbot.export_csv import write_csv
from traderbot.ml.intervals import min_bars_for_forecast_eval


def _synthetic_ohlc(path: Path, n: int, *, step_sec: int = 3600, start_ts: int = 1_700_000_000) -> None:
    rows = []
    for i in range(n):
        ts = start_ts + i * step_sec
        px = 100.0 + i * 0.01
        rows.append(
            {
                "symbol": "TESTIRT",
                "resolution": "60",
                "timestamp": ts,
                "datetime_utc": "2024-01-01T00:00:00+00:00",
                "open": px,
                "high": px + 1,
                "low": px - 1,
                "close": px,
                "volume": 1.0,
            }
        )
    write_csv(path, rows)


def test_contiguous_tail_detects_gap():
    rows = [
        {"timestamp": 0},
        {"timestamp": 3600},
        {"timestamp": 10_800},
    ]
    assert is_contiguous_tail(rows, "60") is False
    assert is_contiguous_tail(rows[:2], "60") is True


def test_recommended_tail_bars_covers_min_eval():
    hb = 24
    assert recommended_tail_bars(hb) >= min_bars_for_forecast_eval(hb)


def test_build_horizon_datasets_complete_per_label(tmp_path: Path):
    ohlc = tmp_path / "ohlc"
    ohlc.mkdir()
    n = recommended_tail_bars(4) + 50
    _synthetic_ohlc(ohlc / "TESTIRT_60.csv", n)

    manifest = build_horizon_datasets(ohlc, tmp_path)
    assert (tmp_path / "horizon_manifest.json").is_file()
    horizons = manifest["horizons"]
    assert "1h" in horizons
    assert horizons["1h"]["files"]
    sample = tmp_path / horizons["1h"]["files"][0]["path"]
    bars = load_bars_csv(sample)
    need = min_bars_for_forecast_eval(1)
    assert len(bars) >= need
    assert is_contiguous_tail(bars, "60")


def test_materialize_from_legacy_flat_dir(tmp_path: Path):
    legacy = tmp_path / "multisource"
    legacy.mkdir()
    _synthetic_ohlc(legacy / "TESTIRT_60.csv", 200)
    root = materialize_crypto_tree(legacy, crypto_root=tmp_path / "crypto")
    assert (root / "ohlc" / "TESTIRT_60.csv").is_file()
    assert (root / "horizons" / "1h" / "TESTIRT_60.csv").is_file()
    data = json.loads((root / "horizon_manifest.json").read_text(encoding="utf-8"))
    assert data["horizons"]["1h"]["files"]
