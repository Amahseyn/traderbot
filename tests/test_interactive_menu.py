import pytest

from traderbot.interactive.menu import MENUS, run_interactive_hub


def test_menus_cover_main_areas():
    titles = {g.title for g in MENUS}
    assert "Charts & compare" in titles
    assert "Data & download" in titles
    assert "Strategies & backtests" in titles
    assert "Auth & API keys" in titles
    charts = next(g for g in MENUS if g.title == "Charts & compare")
    labels = [a.label for a in charts.actions]
    assert any("compare" in label.lower() for label in labels)
    assert any("saved results" in label.lower() for label in labels)


def test_hub_exits_on_zero(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", type("S", (), {"isatty": lambda self: True})())
    monkeypatch.setattr("builtins.input", lambda _p="": "0")
    run_interactive_hub()
    assert "Bye" in capsys.readouterr().err
