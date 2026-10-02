from pathlib import Path

import pytest

from traderbot.export_csv import write_csv
from traderbot.pipelines.registry import get_pipeline, list_pipelines, run_pipeline


def _ohlc_csv(path: Path, n: int = 120) -> None:
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
