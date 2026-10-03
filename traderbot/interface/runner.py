from __future__ import annotations

import sys

from traderbot.interface.pickables import Pickable, pickable_by_id


def run_pickable(pick_id: str, *, dry_run = False) -> list[list[str]]:
    pick = pickable_by_id(pick_id)
    cli_steps = [["traderbot", *argv] for argv in pick.invocations]
    if dry_run:
        return cli_steps

    from traderbot.cli import main as cli_main

    for argv in pick.invocations:
        cli_main(list(argv))
    return cli_steps


def format_invocation(argv: tuple[str, ...]) -> str:
    if not argv:
        return "traderbot"
    return "traderbot " + " ".join(argv)
