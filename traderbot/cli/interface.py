from __future__ import annotations

import argparse
import json
import sys

from traderbot.interface.catalog import catalog_dict
from traderbot.interface.pickables import all_pickables, list_pickable_dicts, pickable_by_id, pickable_to_dict
from traderbot.interface.runner import format_invocation, run_pickable


def _interactive_pick(*, run: bool) -> None:
    picks = all_pickables()
    if not sys.stdin.isatty():
        print(json.dumps(list_pickable_dicts(), indent=2))
        return
    print("Pick a command (number or id):\n", file=sys.stderr)
    for i, p in enumerate(picks, start=1):
        print(f"  {i:2}) {p.id} — {p.title}", file=sys.stderr)
    print(file=sys.stderr)
    try:
        line = input("> ").strip()
    except EOFError:
        raise SystemExit(1) from None
    if not line:
        raise SystemExit(1)
    if line.isdigit():
        idx = int(line) - 1
        if idx < 0 or idx >= len(picks):
            print("invalid number", file=sys.stderr)
            raise SystemExit(1)
        pick_id = picks[idx].id
    else:
        pick_id = line
    if run:
        run_pickable(pick_id)
        return
    pick = pickable_by_id(pick_id)
    for step in pick.invocations:
        print(format_invocation(step))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Discover and run traderbot CLI actions (export, backtest, ML, pipelines).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="Full JSON: command tree, pickables, strategies, models")
    catalog.add_argument("--no-examples", action="store_true")

    list_p = sub.add_parser("list", help="Pickable ids (for scripts and menus)")
    list_p.add_argument("--kind", choices=("workflow", "command", "pipeline"), default=None)
    list_p.add_argument("--tag", default=None, help="Filter by tag (data, ml, strategy, …)")

    describe = sub.add_parser("describe", help="JSON for one pickable id")
    describe.add_argument("id", help="e.g. workflow/download-multisource")

    pick = sub.add_parser("pick", help="Interactive menu (TTY) or JSON list (non-TTY)")
    pick.add_argument("--id", dest="pick_id", default=None, help="Skip menu; show or run this id")
    pick.add_argument("--run", action="store_true", help="Execute invocations via traderbot CLI")

    run = sub.add_parser("run", help="Run a pickable by id")
    run.add_argument("id", help="e.g. strategy/compare-btc60")
    run.add_argument("--dry-run", action="store_true", help="Print shell commands only")

    args = parser.parse_args(argv)

    if args.command == "catalog":
        print(
            json.dumps(
                catalog_dict(include_examples=not args.no_examples),
                indent=2,
            )
        )
        return

    if args.command == "list":
        print(json.dumps(list_pickable_dicts(kind=args.kind, tag=args.tag), indent=2))
        return

    if args.command == "describe":
        try:
            pickable = pickable_by_id(args.id)
        except KeyError:
            print(f"unknown pickable id: {args.id!r}", file=sys.stderr)
            print("hint: traderbot interface list", file=sys.stderr)
            raise SystemExit(1) from None
        print(json.dumps(pickable_to_dict(pickable), indent=2))
        return

    if args.command == "pick":
        if args.pick_id:
            if args.run:
                run_pickable(args.pick_id)
            else:
                pickable = pickable_by_id(args.pick_id)
                for step in pickable.invocations:
                    print(format_invocation(step))
            return
        _interactive_pick(run=args.run)
        return

    if args.command == "run":
        try:
            steps = run_pickable(args.id, dry_run=args.dry_run)
        except KeyError:
            print(f"unknown pickable id: {args.id!r}", file=sys.stderr)
            raise SystemExit(1) from None
        if args.dry_run:
            for cmd in steps:
                print(" ".join(cmd))
        return

    print(f"unknown command {args.command!r}", file=sys.stderr)
    raise SystemExit(1)
