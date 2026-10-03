"""
Full LightGBM matrix: every multisource asset × every default horizon (1m … 1d).

Requires exported data:

    traderbot export --jobs export.jobs.5sources.json --out data/crypto
"""

from __future__ import annotations

from pathlib import Path

import pytest

from traderbot.backtesting import load_bars_csv
from traderbot.data.crypto_store import resolve_crypto_data_dir
from traderbot.ml.intervals import (
    forecast_horizons_for_resolution,
    min_bars_for_forecast_eval,
    resolution_from_csv_path,
    resolution_minutes,
)
from traderbot.ml.pipeline import run_forecast_eval
from traderbot.ml.results import save_run_result
from traderbot.ml.simulator import final_equity_from_curve

REPO_ROOT = Path(__file__).resolve().parents[1]
CRYPTO_OHLC_DIR = resolve_crypto_data_dir()
ALGORITHM = "lightgbm"


def _require_lightgbm():
    try:
        import lightgbm  # noqa: F401
    except (ImportError, OSError) as exc:
        pytest.skip(f"lightgbm unavailable: {exc}")


def _matrix_cases() -> list[tuple[str, int, int, str]]:
    if CRYPTO_OHLC_DIR is None:
        return []
    cases: list[tuple[str, int, int, str]] = []
    for csv_path in sorted(CRYPTO_OHLC_DIR.glob("*.csv")):
        resolution = resolution_from_csv_path(csv_path.name)
        bar_minutes = resolution_minutes(resolution)
        for horizon_bars, horizon_label in forecast_horizons_for_resolution(resolution):
            case_id = f"{csv_path.stem}_{horizon_label}"
            cases.append((csv_path.name, horizon_bars, bar_minutes, case_id))
    return cases


_MATRIX = _matrix_cases()


@pytest.mark.full_matrix
@pytest.mark.parametrize(
    ("csv_name", "horizon_bars", "bar_minutes", "case_id"),
    _MATRIX,
    ids=[c[3] for c in _MATRIX] if _MATRIX else None,
)
def test_lightgbm_asset_horizon_matrix(
    csv_name: str,
    horizon_bars: int,
    bar_minutes: int,
    case_id: str,
    tmp_path: Path,
):
    _require_lightgbm()
    if not _MATRIX:
        pytest.skip("run: traderbot export --jobs export.jobs.5sources.json --out data/crypto")

    from traderbot.ml.models.lightgbm import LightGBMForecastModel

    csv_path = CRYPTO_OHLC_DIR / csv_name
    bars = load_bars_csv(csv_path)
    need = min_bars_for_forecast_eval(horizon_bars)
    if len(bars) < need:
        pytest.skip(f"{csv_name}: need {need} bars, got {len(bars)}")

    result = run_forecast_eval(
        bars,
        LightGBMForecastModel(num_boost_round=20),
        horizon_bars=horizon_bars,
        bar_minutes=bar_minutes,
        train_ratio=0.8,
    )
    assert result.model_id == ALGORITHM
    assert len(result.y_true) == len(result.y_pred) == len(result.timestamps)
    assert result.metrics["n"] >= 5
    assert 0 <= result.metrics["directional_accuracy"] <= 1

    strat = result.extra.get("strategy_equity") or []
    bh = result.extra.get("buy_hold_equity") or []
    assert strat and bh
    assert abs(final_equity_from_curve(strat) - result.metrics["strategy_final_usd"]) < 1e-6
    assert result.metrics["initial_usd"] == 100.0
    assert result.metrics["strategy_final_usd"] > 0
    assert result.metrics["buy_hold_final_usd"] > 0

    out = tmp_path / case_id
    save_run_result(result, out, render_plots=True)
    assert (out / "results.json").is_file()
    vis = result.visualization
    assert vis is not None
    assert vis.actual_vs_predicted.is_file()
    assert vis.sample_equity is not None and vis.sample_equity.is_file()


@pytest.mark.full_matrix
def test_full_matrix_case_count():
    """Guardrail: exported jobs should drive a non-trivial test grid."""
    if CRYPTO_OHLC_DIR is None:
        pytest.skip("crypto OHLC data missing")
    cases = _matrix_cases()
    assert len(cases) >= 40, f"expected >=40 asset×horizon cases, got {len(cases)}"
    assets = {c[0] for c in cases}
    assert len(assets) >= 10
