from pathlib import Path

from traderbot.results.layout import (
    default_ml_batch_out,
    default_strategy_compare_out,
    manifest_parent_dir,
    result_tree_at,
)


def test_result_tree_matches_solution_shape(tmp_path):
    tree = result_tree_at(tmp_path / "exp", run_id="exp")
    run = tree.run_dir("BTCIRT_60", "4h")
    assert run == tree.runs / "BTCIRT_60" / "4h"
    assert tree.reports.is_dir()


def test_default_paths_under_results_root():
    assert default_ml_batch_out(Path("data/crypto/ohlc")).name == "ohlc"
    assert default_strategy_compare_out(Path("data/BTCIRT_60.csv")).parts[-2:] == ("compare", "BTCIRT_60")


def test_manifest_parent_dir(tmp_path):
    root = tmp_path / "exp"
    assert manifest_parent_dir(root / "reports" / "batch_manifest.json") == root.resolve()
    assert manifest_parent_dir(root / "batch_manifest.json") == root.resolve()
