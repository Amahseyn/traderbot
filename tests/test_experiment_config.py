from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from traderbot.pipelines.experiment_config import (
    build_pipeline_kwargs,
    load_experiment_config,
    merge_experiment_params,
    run_experiment_config,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SMOKE_CONFIG = REPO_ROOT / "config" / "experiment.crypto-1h-smoke.json"
LOCAL_CONFIG = REPO_ROOT / "config" / "experiment.crypto-1h-local.json"


def test_load_repo_smoke_experiment():
    config = load_experiment_config(SMOKE_CONFIG)
    assert config.pipeline_id == "crypto-1h-local"
    assert config.status == "pending"
    assert config.params["symbol"] == "BTCIRT"
    assert config.params["model_id"] == "lightgbm"
    assert config.params["run_lightgbm"] is True
    assert config.params["train_supervised_row_count"] == 8
    assert config.params["num_boost_round"] == 50
    assert config.test_steps[0]["params"]["window_hours"] == 24
    assert merge_experiment_params(config, config.test_steps[0])["tail_bars"] == 24


def test_merge_experiment_params_step_overrides_base():
    config = load_experiment_config(LOCAL_CONFIG)
    merged = merge_experiment_params(config, config.test_steps[1])
    assert merged["all_assets"] is True
    assert merged["tail_bars"] == 60
    assert merged["model_id"] == "lightgbm"
    assert merged["run_lightgbm"] is True


def test_build_pipeline_kwargs_maps_paths(tmp_path):
    config = load_experiment_config(SMOKE_CONFIG)
    config.solution_root = str(tmp_path / "custom_solution")
    merged = merge_experiment_params(config, config.test_steps[0])
    kwargs = build_pipeline_kwargs(
        config,
        param_overrides=merged,
        results_dir=tmp_path / "custom_solution",
    )
    assert kwargs["symbol"] == "BTCIRT"
    assert kwargs["tail_bars"] == 24
    assert kwargs["train_supervised_row_count"] == 8
    assert kwargs["num_boost_round"] == 50
    assert kwargs["results_dir"] == tmp_path / "custom_solution"


def test_run_experiment_dry_run():
    out = run_experiment_config(SMOKE_CONFIG, dry_run=True)
    assert out["dry_run"] is True
    assert out["pipeline_id"] == "crypto-1h-local"
    assert out["test_steps"][0]["params"]["window_hours"] == 24
    assert out["test_steps"][0]["params"]["tail_bars"] == 24
    assert "kwargs" in out


def test_run_experiment_multi_step_dry_run():
    out = run_experiment_config(LOCAL_CONFIG, dry_run=True)
    step_ids = [row["step_id"] for row in out["test_steps"]]
    assert step_ids == ["hours-24", "hours-60", "full-ohlc"]
    assert out["test_steps"][2]["params"]["window_hours"] is None
    assert out["test_steps"][2]["params"]["tail_bars"] is None
    assert out["test_steps"][2]["params"]["model_id"] == "lightgbm"
    assert out["test_steps"][2]["params"]["run_lightgbm"] is True


def test_run_experiment_smoke_updates_status(tmp_path):
    pytest.importorskip("matplotlib")
    from traderbot.data.crypto_store import resolve_crypto_data_dir

    if resolve_crypto_data_dir() is None:
        pytest.skip("no crypto OHLC")

    config_path = tmp_path / "smoke.json"
    shutil.copy(SMOKE_CONFIG, config_path)
    out = run_experiment_config(config_path, force=True)
    assert out["skipped"] is False
    assert out["status"] == "completed"

    saved = json.loads(config_path.read_text())
    assert saved["status"] == "completed"
    assert saved["test_steps"][0]["status"] == "completed"
    assert saved["completed_at_utc"]
    assert saved["result_solution_root"]

    report = Path(saved["result_solution_root"]) / "reports" / "experiment_config.json"
    assert report.is_file()


def test_run_experiment_skips_when_completed(tmp_path):
    config_path = tmp_path / "done.json"
    shutil.copy(SMOKE_CONFIG, config_path)
    data = json.loads(config_path.read_text())
    data["status"] = "completed"
    data["test_steps"][0]["status"] = "completed"
    data["result_solution_root"] = str(tmp_path / "solutions")
    config_path.write_text(json.dumps(data, indent=2))

    out = run_experiment_config(config_path)
    assert out["skipped"] is True
    assert out["reason"] == "already completed"
