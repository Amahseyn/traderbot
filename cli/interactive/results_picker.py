from __future__ import annotations

import sys
from pathlib import Path

from traderbot.results.discover import ResultChoice, ResultGroup, discover_result_groups, subchoices_for_run


def _print_run_line(index: int, run: ResultChoice) -> None:
    suffix = f" — {run.detail}" if run.detail else ""
    print(f"  {index}) {run.label}{suffix}", file=sys.stderr)
    print(f"      {run.path}", file=sys.stderr)


def _pick_from_list(prompt: str, count: int) -> int | None:
    line = input(prompt).strip()
    if line in ("0", "b", "back", "q"):
        return None
    if not line.isdigit():
        return -1
    idx = int(line) - 1
    if idx < 0 or idx >= count:
        return -1
    return idx


def _pick_group(groups: list[ResultGroup]) -> ResultGroup | str | None:
    print("\nWhat kind of results?\n", file=sys.stderr)
    for i, group in enumerate(groups, start=1):
        print(f"  {i}) {group.title} ({len(group.runs)})", file=sys.stderr)
    manual_idx = len(groups) + 1
    print(f"  {manual_idx}) Enter path manually", file=sys.stderr)
    print("  0) Cancel\n", file=sys.stderr)
    line = input("Category: ").strip()
    if line in ("0", "b", "back", "q"):
        return None
    if not line.isdigit():
        return None
    n = int(line)
    if n == manual_idx:
        return "manual"
    idx = n - 1
    if idx < 0 or idx >= len(groups):
        return None
    return groups[idx]


def _pick_run(group: ResultGroup) -> ResultChoice | None:
    print(f"\n{group.title}:\n", file=sys.stderr)
    for i, run in enumerate(group.runs, start=1):
        _print_run_line(i, run)
    print("  0) Back\n", file=sys.stderr)
    idx = _pick_from_list("Run: ", len(group.runs))
    if idx is None or idx < 0:
        return None
    return group.runs[idx]


def _pick_subchoice(group: ResultGroup, run: ResultChoice) -> ResultChoice | None:
    sub = subchoices_for_run(group, run)
    if not sub:
        return run
    if len(sub) == 1:
        return sub[0]
    print(f"\n{run.label} — what to view?\n", file=sys.stderr)
    for i, choice in enumerate(sub, start=1):
        _print_run_line(i, choice)
    print("  0) Back\n", file=sys.stderr)
    idx = _pick_from_list("View: ", len(sub))
    if idx is None or idx < 0:
        return None
    return sub[idx]


def _prompt_custom_path() -> Path | None:
    line = input("Directory path (empty=cancel): ").strip()
    if not line:
        return None
    path = Path(line).expanduser()
    if not path.exists():
        print(f"not found: {path}", file=sys.stderr)
        return None
    return path.resolve()


def pick_result_directory(
    *,
    results_root: Path = Path("results"),
    solutions_root: Path = Path("solutions"),
) -> Path | None:
    groups = discover_result_groups(results_root=results_root, solutions_root=solutions_root)
    while True:
        if groups:
            group = _pick_group(groups)
            if group is None:
                return None
            if group == "manual":
                return _prompt_custom_path()
            run = _pick_run(group)
            if run is None:
                continue
            target = _pick_subchoice(group, run)
            if target is None:
                continue
            return target.path

        print("\nNo chart outputs found under results/ or solutions/.", file=sys.stderr)
        print("Run a compare, backtest, or data live command first.\n", file=sys.stderr)
        custom = input("Enter results directory manually? [y/N]: ").strip().lower()
        if custom in ("y", "yes"):
            return _prompt_custom_path()
        return None


def pick_plots_view_mode() -> str:
    mode = input("Open in viewer, matplotlib, or list paths? [open/show/list]: ").strip().lower()
    if mode in ("show", "s", "matplotlib", "mpl"):
        return "--show"
    if mode in ("list", "l"):
        return ""
    return "--open"
