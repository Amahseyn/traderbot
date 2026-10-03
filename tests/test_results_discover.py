import json

from traderbot.results.discover import discover_result_groups, subchoices_for_run


def test_discover_compare_and_strategy_subchoices(tmp_path):
    compare = tmp_path / "compare_BTCIRT_60"
    reports = compare / "reports"
    reports.mkdir(parents=True)
    viz = compare / "visualizations"
    viz.mkdir()
    (viz / "strategy_ranking.png").write_bytes(b"x")
    strat_dir = compare / "runs" / "sma_cross"
    strat_dir.mkdir(parents=True)
    sv = strat_dir / "visualizations"
    sv.mkdir()
    (sv / "equity_curve.png").write_bytes(b"y")
    (strat_dir / "backtest_summary.json").write_text(
        json.dumps({"algorithm": "sma_cross", "return_pct": 1.5, "visualization": {}}),
        encoding="utf-8",
    )
    (reports / "compare_manifest.json").write_text(
        json.dumps(
            {
                "csv": str(tmp_path / "btc.csv"),
                "best_strategy_id": "sma_cross",
                "strategies": [{"strategy_id": "sma_cross", "return_pct": 1.5}],
            }
        ),
        encoding="utf-8",
    )
    groups = discover_result_groups(results_root=tmp_path, solutions_root=tmp_path / "none")
    kinds = {g.kind for g in groups}
    assert "compare" in kinds
    compare_group = next(g for g in groups if g.kind == "compare")
    assert compare_group.runs[0].label == "compare_BTCIRT_60"
    sub = subchoices_for_run(compare_group, compare_group.runs[0])
    assert sub is not None
    assert sub[0].label == "Overview"
    assert any(c.label == "sma_cross" for c in sub)


def test_discover_legacy_compare_layout(tmp_path):
    """Pre-structure compare folders still appear in the picker."""
    compare = tmp_path / "legacy_compare"
    compare.mkdir()
    viz = compare / "visualizations"
    viz.mkdir()
    (viz / "strategy_ranking.png").write_bytes(b"x")
    strat_dir = compare / "btc_sma_cross"
    strat_dir.mkdir()
    (strat_dir / "visualizations" / "equity_curve.png").parent.mkdir(parents=True)
    (strat_dir / "visualizations" / "equity_curve.png").write_bytes(b"y")
    (strat_dir / "backtest_summary.json").write_text(
        json.dumps({"algorithm": "sma_cross", "return_pct": 1.0, "visualization": {}}),
        encoding="utf-8",
    )
    (compare / "compare_manifest.json").write_text(
        json.dumps(
            {
                "csv": str(tmp_path / "btc.csv"),
                "strategies": [{"strategy_id": "sma_cross", "return_pct": 1.0}],
            }
        ),
        encoding="utf-8",
    )
    groups = discover_result_groups(results_root=tmp_path, solutions_root=tmp_path / "none")
    compare_group = next(g for g in groups if g.kind == "compare")
    sub = subchoices_for_run(compare_group, compare_group.runs[0])
    assert sub is not None
    assert any(c.label == "sma_cross" for c in sub)


def test_discover_ml_batch_under_reports(tmp_path):
    batch_root = tmp_path / "ml_batch"
    run = batch_root / "runs" / "BTCIRT_60" / "4h"
    viz = run / "visualizations"
    viz.mkdir(parents=True)
    (viz / "actual_vs_predicted.png").write_bytes(b"x")
    (run / "results.json").write_text(
        json.dumps({"model_id": "lightgbm", "horizon_label": "4h", "n_samples": 10}),
        encoding="utf-8",
    )
    reports = batch_root / "reports"
    reports.mkdir(parents=True)
    (reports / "batch_manifest.json").write_text(
        json.dumps(
            {
                "model_id": "lightgbm",
                "run_count": 1,
                "runs": [{"dataset": "BTCIRT_60", "horizon_label": "4h", "out_dir": str(run)}],
            }
        ),
        encoding="utf-8",
    )
    groups = discover_result_groups(results_root=tmp_path, solutions_root=tmp_path / "none")
    ml_batch = next(g for g in groups if g.kind == "ml_batch")
    assert ml_batch.runs[0].path == batch_root.resolve()
    sub = subchoices_for_run(ml_batch, ml_batch.runs[0])
    assert sub is not None
    assert any("BTCIRT_60" in c.label for c in sub)


def test_discover_single_backtest_not_under_compare(tmp_path):
    run = tmp_path / "backtest_sma"
    run.mkdir()
    viz = run / "visualizations"
    viz.mkdir()
    (viz / "equity_curve.png").write_bytes(b"x")
    (run / "backtest_summary.json").write_text(
        json.dumps({"algorithm": "sma_cross", "return_pct": 2.0}),
        encoding="utf-8",
    )
    groups = discover_result_groups(results_root=tmp_path, solutions_root=tmp_path / "none")
    backtest = next(g for g in groups if g.kind == "backtest")
    assert backtest.runs[0].path == run.resolve()
