from __future__ import annotations

import argparse
import sys

from traderbot.interactive.menu import run_interactive_hub


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Interactive traderbot menu (prompts and run commands).",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="menu",
        choices=("menu",),
        help="Open the interactive menu (default)",
    )
    args = parser.parse_args(argv)

    if args.command == "menu":
        run_interactive_hub()
        return

    print(f"unknown command {args.command!r}", file=sys.stderr)
    raise SystemExit(1)
