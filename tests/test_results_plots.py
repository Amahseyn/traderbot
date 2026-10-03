import json
from pathlib import Path

import pytest

from traderbot.data_cli import main as data_main
from traderbot.results.plots import discover_result_plots, results_plots_catalog


def test_discover_from_compare_manifest_in_reports(tmp_path):
    viz = tmp_path / "visualizations"
    viz.mkdir()
    ranking = viz / "strategy_ranking.png"
    ranking.write_bytes(b"png")
    reports = tmp_path / "reports"
    reports.mkdir()
    manifest = {
        "visualization": {
            "strategy_ranking": str(ranking),
        }
    }
    (reports / "compare_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    plots = discover_result_plots(tmp_path)
    assert plots == [ranking.resolve()]


def test_discover_from_compare_manifest(tmp_path):
    viz = tmp_path / "visualizations"
    viz.mkdir()
    ranking = viz / "strategy_ranking.png"
    ranking.write_bytes(b"png")
    manifest = {
        "visualization": {
            "strategy_ranking": str(ranking),
            "equity_overlay": str(viz / "missing.png"),
        }
    }
    (tmp_path / "compare_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    plots = discover_result_plots(tmp_path)
    assert plots == [ranking.resolve()]


def test_discover_visualizations_dir_only(tmp_path):
    viz = tmp_path / "visualizations"
    viz.mkdir()
    a = viz / "equity_curve.png"
    b = viz / "drawdown.png"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    plots = discover_result_plots(tmp_path)
    assert plots == sorted([a.resolve(), b.resolve()], key=lambda p: p.name)


def test_data_plots_json_lists_paths(tmp_path, capsys):
    viz = tmp_path / "visualizations"
    viz.mkdir()
    png = viz / "actual_vs_predicted.png"
    png.write_bytes(b"x")
    (tmp_path / "results.json").write_text("{}", encoding="utf-8")
    data_main(["plots", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["plot_count"] == 1
    assert payload["plots"] == [str(png.resolve())]


def test_data_plots_missing_dir_exits():
    from traderbot.data_cli import main as data_main

    with pytest.raises(SystemExit) as exc:
        data_main(["plots", "/nonexistent/run"])
    assert exc.value.code == 1


def test_data_plots_no_charts_exits(tmp_path):
    with pytest.raises(SystemExit) as exc:
        data_main(["plots", str(tmp_path)])
    assert exc.value.code == 1


def test_results_plots_catalog_root(tmp_path):
    catalog = results_plots_catalog(tmp_path)
    assert catalog["plot_count"] == 0
    assert catalog["root"] == str(tmp_path.resolve())
