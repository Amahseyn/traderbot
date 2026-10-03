from pathlib import Path

import pytest

from traderbot.data.crypto_store import resolve_crypto_data_dir
from traderbot.data.export import write_csv
from traderbot.pipelines.registry import get_pipeline, list_pipelines, run_pipeline
from traderbot.utils.constants import CRYPTO_1H_SMOKE_TAIL_BARS


def _ohlc_csv(path: Path, n = 120) -> None:
    rows = []
    for i in range(n):
        c = 100.0 + i * 0.05
        rows.append(
            {
                "symbol": "TEST",
                "resolution": "60",
                "timestamp": 1_700_000_000 + i * 3600,
                "datetime_utc": "",
                "open": c,
                "high": c + 1,
                "low": c - 1,
                "close": c,
                "volume": 1000.0,
            }
        )
    write_csv(path, rows)


def test_pipeline_registry_lists_seven():
    ids = {p.id for p in list_pipelines()}
    assert "full-research-lightgbm" in ids
    assert "sma-backtest" in ids
    assert len(ids) >= 7


def test_sma_backtest_pipeline(tmp_path):
    csv_path = tmp_path / "TEST_60.csv"
    _ohlc_csv(csv_path)
    out = tmp_path / "bt"
    result = run_pipeline("sma-backtest", csv_path=csv_path, results_dir=out)
    assert result.pipeline_id == "sma-backtest"
    assert "return_pct" in result.outputs
    assert "solution_root" in result.outputs
    reports = Path(result.outputs["solution_root"]) / "reports"
    assert (reports / "pipeline_summary.json").is_file()


def test_lightgbm_single_asset_pipeline(tmp_path):
    pytest.importorskip("lightgbm")
    try:
        import lightgbm  # noqa: F401
    except OSError as exc:
        pytest.skip(str(exc))
    pytest.importorskip("matplotlib")

    csv_path = tmp_path / "TEST_60.csv"
    _ohlc_csv(csv_path, n=150)
    out = tmp_path / "ml"
    result = run_pipeline(
        "lightgbm-single-asset",
        csv_path=csv_path,
        results_dir=out,
        all_horizons=True,
    )
    assert result.outputs["runs"]
    assert "solution_root" in result.outputs
    reports = Path(result.outputs["solution_root"]) / "reports"
    assert (reports / "pipeline_summary.json").is_file()


def test_lightgbm_multisource_default_uses_existing_csv(tmp_path):
    pytest.importorskip("lightgbm")
    try:
        import lightgbm  # noqa: F401
    except OSError as exc:
        pytest.skip(str(exc))
    pytest.importorskip("matplotlib")

    data = tmp_path / "data"
    data.mkdir()
    _ohlc_csv(data / "TEST_60.csv", n=150)
    out = tmp_path / "results"
    result = run_pipeline(
        "lightgbm-multisource-default",
        data_dir=data,
        skip_export=True,
        solutions_root=out,
    )
    assert result.outputs["run_count"] == 1
    reports = Path(result.outputs["solution_root"]) / "reports"
    assert (reports / "batch_manifest.json").is_file()


def test_get_pipeline_unknown():
    with pytest.raises(KeyError):
        get_pipeline("not-a-pipeline")


def test_crypto_1h_local_pipeline_uses_existing_csv(tmp_path):
    pytest.importorskip("matplotlib")
    ohlc_dir = resolve_crypto_data_dir()
    if ohlc_dir is None:
        pytest.skip("no crypto OHLC; export BTC 1h first")
    btc_csv = ohlc_dir / "BTCIRT_60.csv"
    if not btc_csv.is_file():
        pytest.skip("missing BTCIRT_60.csv")

    out = tmp_path / "btc_local"
    result = run_pipeline(
        "crypto-1h-local",
        csv_path=btc_csv,
        results_dir=out,
        tail_bars=CRYPTO_1H_SMOKE_TAIL_BARS,
        run_lightgbm=False,
    )
    assert result.pipeline_id == "crypto-1h-local"
    assert result.outputs["bar_count"] == CRYPTO_1H_SMOKE_TAIL_BARS
    assert result.outputs["best_strategy_id"]
    reports = out / "reports"
    assert (reports / "pipeline_summary.json").is_file()
    assert any(step.name == "strategy_compare" for step in result.steps)
    assert result.outputs["min_bars_lightgbm"] > CRYPTO_1H_SMOKE_TAIL_BARS
    assert result.outputs["lightgbm_ran"] is False
    assert not any(step.name.startswith("lightgbm") for step in result.steps)


def test_crypto_1h_local_pipeline_full_csv_runs_lightgbm(tmp_path):
    pytest.importorskip("lightgbm")
    try:
        import lightgbm  # noqa: F401
    except OSError as exc:
        pytest.skip(str(exc))
    pytest.importorskip("matplotlib")

    ohlc_dir = resolve_crypto_data_dir()
    if ohlc_dir is None:
        pytest.skip("no crypto OHLC")
    btc_csv = ohlc_dir / "BTCIRT_60.csv"
    if not btc_csv.is_file():
        pytest.skip("missing BTCIRT_60.csv")

    out = tmp_path / "btc_full"
    result = run_pipeline(
        "crypto-1h-local",
        csv_path=btc_csv,
        results_dir=out,
        tail_bars=None,
        run_lightgbm=True,
    )
    assert result.outputs["bar_count"] >= result.outputs["min_bars_lightgbm"]
    assert result.outputs["lightgbm_ran"] is True
    assert any(step.name == "lightgbm" for step in result.steps)
