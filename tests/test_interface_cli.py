import json

import pytest

from traderbot.interface.pickables import all_pickables
from traderbot.cli.interface import main as interface_main


def test_interface_catalog_complete(capsys):
    interface_main(["catalog"])
    out = json.loads(capsys.readouterr().out)
    assert out["schema_version"] == 1
    assert out["command_tree"]
    assert out["pickables"]
    assert out["strategies"]
    assert out["models"]
    ids = [p["id"] for p in out["pickables"]]
    assert len(ids) == len(set(ids))
    assert "workflow/download-multisource" in ids
    assert "workflow/crypto-1h-local-research" in ids
    assert "terminal" in {c["id"] for c in out["top_level_commands"]}


def test_interface_catalog_no_examples(capsys):
    interface_main(["catalog", "--no-examples"])
    out = json.loads(capsys.readouterr().out)
    assert "examples" not in out


def test_interface_list_and_describe(capsys):
    interface_main(["list", "--tag", "visualization"])
    listed = json.loads(capsys.readouterr().out)
    assert listed
    pick_id = listed[0]["id"]
    interface_main(["describe", pick_id])
    detail = json.loads(capsys.readouterr().out)
    assert detail["id"] == pick_id
    assert detail["cli_steps"]


def test_interface_run_dry_run(capsys):
    interface_main(["run", "workflow/download-multisource", "--dry-run"])
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("traderbot export")


def test_interface_run_invokes_cli(monkeypatch):
    seen: list[list[str]] = []

    def fake_main(argv):
        seen.append(list(argv))

    monkeypatch.setattr("traderbot.cli.main", fake_main)
    interface_main(["run", "command/strategy/catalog"])
    assert seen == [["strategy", "catalog", "--implemented-only"]]


def test_interface_pick_by_id(capsys):
    interface_main(["pick", "--id", "command/ml/catalog"])
    assert "traderbot ml catalog" in capsys.readouterr().out


def test_interface_pick_unknown_id():
    with pytest.raises(SystemExit):
        interface_main(["run", "no/such-id"])


def test_all_pickables_cover_pipelines():
    from traderbot.pipelines.registry import list_pipelines

    pick_ids = {p.id for p in all_pickables()}
    for pipe in list_pipelines():
        assert f"pipeline/run/{pipe.id}" in pick_ids
