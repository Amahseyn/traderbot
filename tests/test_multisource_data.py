"""Multi-market export jobs and per-CSV ML smoke tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from traderbot.backtesting import load_bars_csv
from traderbot.data.crypto_store import recommended_tail_bars, resolve_crypto_data_dir
from traderbot.data.export import load_jobs
from traderbot.markets.market_data import RESOLUTIONS
from traderbot.ml.batch import run_batch_on_directory
from traderbot.ml.intervals import default_eval_horizon
from traderbot.ml.pipeline import run_forecast_eval
from traderbot.ml.results import save_run_result

REPO_ROOT = Path(__file__).resolve().parents[1]
JOBS_FILE = REPO_ROOT / "export.jobs.5sources.json"
CRYPTO_OHLC_DIR = resolve_crypto_data_dir()

FIVE_SOURCES = {"BTCIRT", "ETHIRT", "ETHUSDT", "XRPIRT", "LTCIRT"}


def test_five_source_jobs_cover_all_intervals():
    jobs = load_jobs(JOBS_FILE)
    symbols = {j["symbol"] for j in jobs}
    intervals = {j["interval"] for j in jobs}
    assert symbols == FIVE_SOURCES
    assert intervals == set(RESOLUTIONS)


def test_multisource_csvs_exist():
    if CRYPTO_OHLC_DIR is None:
        pytest.skip("run: traderbot export --jobs export.jobs.5sources.json --out data/crypto")
    csvs = sorted(CRYPTO_OHLC_DIR.glob("*.csv"))
    assert len(csvs) >= len(load_jobs(JOBS_FILE))
    for path in csvs:
        bars = load_bars_csv(path)
        assert len(bars) > 0
        assert "close" in bars[0]


def _require_lightgbm():
    try:
        import lightgbm  # noqa: F401
    except (ImportError, OSError) as exc:
        pytest.skip(f"lightgbm unavailable: {exc}")


def _multisource_csv_paths() -> list[Path]:
    if CRYPTO_OHLC_DIR is None:
        return []
    return sorted(CRYPTO_OHLC_DIR.glob("*.csv"))


def test_lightgbm_smoke_on_each_export(tmp_path):
    _require_lightgbm()
    pytest.importorskip("matplotlib")
    from traderbot.ml.models.lightgbm import LightGBMForecastModel

    paths = _multisource_csv_paths()
    if not paths:
        pytest.skip("run: traderbot export --jobs export.jobs.5sources.json --out data/crypto")

    tested = 0
    for csv_path in paths:
        bars = load_bars_csv(csv_path)
        if len(bars) < 50:
            continue
        resolution = csv_path.stem.split("_")[-1]
        horizon, bar_minutes = default_eval_horizon(resolution)
        result = run_forecast_eval(
            bars,
            LightGBMForecastModel(num_boost_round=15),
            horizon_bars=horizon,
            bar_minutes=bar_minutes,
            train_ratio=0.8,
        )
        out = tmp_path / csv_path.stem
        save_run_result(result, out)
        assert result.metrics["n"] >= 5
        assert len(result.y_true) == len(result.y_pred)
        assert result.visualization is not None
        assert result.visualization.actual_vs_predicted.is_file()
        assert result.visualization.residuals.is_file()
        assert result.visualization.feature_importance is not None
        assert result.visualization.sample_equity is not None
        assert result.visualization.sample_equity.is_file()
        assert "strategy_final_usd" in result.metrics
        tested += 1
    assert tested >= 1, "no CSV had enough bars for ML smoke test"


def test_batch_writes_visualization_manifest(tmp_path):
    _require_lightgbm()
    pytest.importorskip("matplotlib")
    paths = _multisource_csv_paths()
    if not paths:
        pytest.skip("multisource data missing")
    # Use one small subset dir
    subset = tmp_path / "csv"
    subset.mkdir()
    for p in paths[:2]:
        subset.joinpath(p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "results"
    from traderbot.solutions.layout import prepare_solution

    layout = prepare_solution("test-batch", solutions_root=out)
    results = run_batch_on_directory(subset, layout=layout, num_boost_round=10, all_horizons=True)
    assert len(results) >= 2
    assert (layout.reports / "batch_manifest.json").is_file()
    first = results[0]
    assert first.visualization is not None
    assert first.visualization.actual_vs_predicted.is_file()


def test_crypto_horizon_slices_when_present():
    root = REPO_ROOT / "data" / "crypto"
    manifest_path = root / "horizon_manifest.json"
    if not manifest_path.is_file():
        pytest.skip("run: traderbot data horizons")
    from traderbot.ml.intervals import DEFAULT_FORECAST_HORIZONS

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    for _minutes, label in DEFAULT_FORECAST_HORIZONS:
        files = data.get("horizons", {}).get(label, {}).get("files", [])
        if not files:
            continue
        for entry in files:
            path = root / entry["path"]
            bars = load_bars_csv(path)
            assert len(bars) == entry["rows"]
            assert len(bars) >= recommended_tail_bars(entry["horizon_bars"])


def test_multisource_results_manifest_optional():
    if CRYPTO_OHLC_DIR is None:
        pytest.skip("no crypto OHLC data")
    manifest = CRYPTO_OHLC_DIR.parent / "export_manifest.json"
    if not manifest.is_file():
        manifest = CRYPTO_OHLC_DIR / "export_manifest.json"  # legacy flat export
    if not manifest.is_file():
        pytest.skip("manifest written by export script")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["sources"] == sorted(FIVE_SOURCES)
    assert len(data["files"]) >= 1
