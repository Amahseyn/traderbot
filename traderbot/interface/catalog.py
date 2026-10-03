from __future__ import annotations

from dataclasses import asdict

from traderbot.algorithms.registry import list_strategies
from traderbot.interface.command_tree import command_tree
from traderbot.interface.pickables import all_pickables as _all_pickables
from traderbot.interface.pickables import list_pickable_dicts, pickable_to_dict
from traderbot.interface.runner import format_invocation
from traderbot.ml.registry import list_models
from traderbot.pipelines.registry import list_pipelines


def catalog_dict(*, include_examples: bool = True) -> dict:
    from traderbot.cli import _COMMANDS, _register_commands

    _register_commands()
    top_level = [
        {"id": name, "summary": help_text}
        for name, (help_text, _) in sorted(_COMMANDS.items())
    ]
    pickables = [pickable_to_dict(p) for p in _all_pickables()]
    body: dict = {
        "schema_version": 1,
        "top_level_commands": top_level,
        "command_tree": command_tree(),
        "pickables": pickables,
        "pickable_index": list_pickable_dicts(),
        "strategies": [asdict(s) for s in list_strategies(implemented_only=False)],
        "models": [asdict(m) for m in list_models(implemented_only=False)],
        "pipelines": [
            {"id": p.id, "title": p.title, "description": p.description}
            for p in list_pipelines()
        ],
        "nested_catalogs": {
            "strategies": "traderbot strategy catalog [--implemented-only]",
            "models": "traderbot ml catalog [--implemented-only]",
            "terminal": "traderbot terminal catalog",
            "pick": "traderbot interface list | pick | run <id>",
        },
    }
    if include_examples:
        body["examples"] = [
            format_invocation(p.invocations[0]) for p in _all_pickables() if p.invocations
        ][:12]
    return body
