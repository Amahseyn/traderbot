"""Crypto export jobs and on-disk CSV smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from traderbot.backtesting import load_bars_csv
from traderbot.data.crypto_store import recommended_tail_bars, resolve_crypto_data_dir
from traderbot.data.export import load_jobs

REPO_ROOT = Path(__file__).resolve().parents[1]
JOBS_FILE = REPO_ROOT / "export.jobs.example.json"
CRYPTO_OHLC_DIR = resolve_crypto_data_dir()


def test_export_jobs_example_file():
    jobs = load_jobs(JOBS_FILE)
    assert len(jobs) >= 1
    symbols = {j["symbol"] for j in jobs}
    assert "BTCIRT" in symbols
    assert all(j.get("interval") for j in jobs)


def test_crypto_ohlc_csvs_exist():
    if CRYPTO_OHLC_DIR is None:
        pytest.skip("run: traderbot export --jobs export.jobs.example.json --out data/crypto")
    jobs = load_jobs(JOBS_FILE)
    csvs = sorted(CRYPTO_OHLC_DIR.glob("*.csv"))
    if len(csvs) < len(jobs):
        pytest.skip("partial crypto OHLC export; run export with export.jobs.example.json")
    for path in csvs:
        bars = load_bars_csv(path)
        assert len(bars) > 0
        assert "close" in bars[0]


def test_crypto_horizon_slices_when_present():
    root = REPO_ROOT / "data" / "crypto"
    manifest_path = root / "horizon_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("run: traderbot data horizons")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    horizons = data.get("horizons", {})
    if not horizons:
        pytest.skip("no horizon slices in manifest")
    for label, block in horizons.items():
        files = block.get("files", [])
        if not files:
            continue
        for entry in files:
            path = root / entry["path"]
            assert path.is_file(), f"missing horizon slice {path}"
            bars = load_bars_csv(path)
            assert len(bars) > 0
        break


def test_recommended_tail_bars_positive():
    assert recommended_tail_bars(4) > 0
