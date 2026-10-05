from traderbot.solutions.layout import prepare_solution, solution_slug


def test_solution_slug():
    assert solution_slug("full-research-strategies") == "full_research_strategies"


def test_prepare_solution_tree(tmp_path):
    layout = prepare_solution("test-pipeline", solutions_root=tmp_path, title="Test")
    assert layout.root == tmp_path / "test_pipeline"
    assert layout.data.is_dir()
    assert layout.runs.is_dir()
    assert layout.reports.is_dir()
    assert (layout.root / "README.md").is_file()
    assert (layout.reports / "solution_meta.json").is_file()

    run = layout.run_dir("BTCIRT_60", "4h")
    assert run == layout.runs / "BTCIRT_60" / "4h"
    viz = layout.visualizations_dir(run)
    assert viz.name == "visualizations"
