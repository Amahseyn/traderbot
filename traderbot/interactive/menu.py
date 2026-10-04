from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from traderbot.interface.pickables import all_pickables
from traderbot.interface.runner import format_invocation, run_pickable

Argv = list[str]
ArgvFn = Callable[[], Argv | None]


@dataclass(frozen=True, slots=True)
class MenuAction:
    label: str
    argv: Argv | ArgvFn
    hint: str = ""


@dataclass(frozen=True, slots=True)
class MenuGroup:
    title: str
    actions: tuple[MenuAction, ...]


def _default_csv() -> str:
    p = Path("data/crypto/ohlc/BTCIRT_60.csv")
    return str(p) if p.is_file() else "data/crypto/ohlc/BTCIRT_60.csv"


def _prompt_path(label: str, default: str) -> str:
    line = input(f"{label} [{default}]: ").strip()
    return line or default


def _compare_argv(*, with_filters = False) -> Argv:
    csv = _prompt_path("OHLC CSV", _default_csv())
    out = _prompt_path("Output dir", "results/strategies/compare/BTCIRT_60")
    argv: Argv = [
        "strategy",
        "compare",
        csv,
        "--out",
        out,
        "--visualize",
    ]
    if with_filters:
        ctx = input("context-bars [3]: ").strip() or "3"
        argv.extend(["--context-bars", ctx])
        argv.extend(["--buy-min-recent-return", "-0.03"])
        if input("price-confirm for SMA/EMA? [y/N]: ").strip().lower() in ("y", "yes"):
            argv.append("--price-confirm")
    return argv


def _compare_argv_filtered() -> Argv:
    return _compare_argv(with_filters=True)


def _strategy_backtest_viz_argv() -> Argv:
    strategy = input("Strategy id [sma_cross]: ").strip() or "sma_cross"
    csv = _prompt_path("OHLC CSV", _default_csv())
    out = _prompt_path("Output dir", f"results/strategies/backtest/btc_{strategy}")
    return [
        "strategy",
        "backtest",
        csv,
        "--strategy",
        strategy,
        "--out",
        out,
        "--visualize",
    ]


def _view_saved_results_argv() -> Argv | None:
    from traderbot.interactive.results_picker import pick_plots_view_mode, pick_result_directory

    root = pick_result_directory()
    if root is None:
        return None
    argv: Argv = ["data", "plots", str(root)]
    mode_flag = pick_plots_view_mode()
    if mode_flag:
        argv.append(mode_flag)
    return argv


def _live_chart_argv() -> Argv:
    interval = input("UDF interval [60]: ").strip() or "60"
    bars = input("Bars per market [96]: ").strip() or "96"
    out = _prompt_path("Output dir", "results/data/live")
    return ["data", "live", "--interval", interval, "--bars", bars, "--out", out]


def _live_watch_argv() -> Argv:
    interval = input("UDF interval [60]: ").strip() or "60"
    poll = input("Refresh seconds [60]: ").strip() or "60"
    out = _prompt_path("Output dir", "results/data/live")
    return [
        "data",
        "live",
        "--interval",
        interval,
        "--bars",
        "48",
        "--poll-sec",
        poll,
        "--out",
        out,
    ]


def _export_btc_argv() -> Argv:
    days = input("History days [30]: ").strip() or "30"
    out = _prompt_path("Output dir", "data/crypto")
    return [
        "export",
        "--src",
        "btc",
        "--dst",
        "rls",
        "--interval",
        "60",
        "--days",
        days,
        "--out",
        out,
    ]


def _ml_run_argv() -> Argv:
    csv = _prompt_path("OHLC CSV", _default_csv())
    model = input("Model [lightgbm]: ").strip() or "lightgbm"
    horizon = input("Horizon bars [4]: ").strip() or "4"
    test_bars = input("Test steps — holdout tail bars (empty=train-ratio split): ").strip()
    train_samples = input("Training samples — supervised rows (empty=train-ratio split): ").strip()
    out = _prompt_path("Results dir", "results/ml/btc_60")
    argv: Argv = ["ml", "run", csv, "--model", model, "--horizon-bars", horizon, "--out", out]
    if test_bars:
        argv.extend(["--holdout-tail-bars", test_bars])
    if train_samples:
        argv.extend(["--train-samples", train_samples])
    return argv


def _ml_batch_viz_argv() -> Argv:
    folder = _prompt_path("CSV directory", "data/crypto/horizons/4h")
    out = _prompt_path("Results dir", "results/ml/horizons_4h")
    model = input("Model [lightgbm]: ").strip() or "lightgbm"
    argv: Argv = ["ml", "batch", folder, "--model", model, "--out", out]
    if input("All forecast horizons per file? [Y/n]: ").strip().lower() not in ("n", "no"):
        argv.append("--all-horizons")
    return argv


def _run_pickable_workflow(pick_id: str) -> Argv | None:
    confirm = input(f"Run workflow {pick_id}? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        return None
    run_pickable(pick_id)
    return None


def _pick_visualization_workflow() -> Argv | None:
    from traderbot.interface.pickables import list_pickable_dicts

    rows = list_pickable_dicts(tag="visualization")
    print("\nVisualization workflows:\n", file=sys.stderr)
    for i, row in enumerate(rows, start=1):
        print(f"  {i:2}) {row['id']} — {row['title']}", file=sys.stderr)
    line = input("Number or id (empty=cancel): ").strip()
    if not line:
        return None
    if line.isdigit():
        idx = int(line) - 1
        if idx < 0 or idx >= len(rows):
            return None
        pick_id = rows[idx]["id"]
    else:
        pick_id = line
    confirm = input("Run this workflow? [y/N]: ").strip().lower()
    if confirm not in ("y", "yes"):
        return None
    run_pickable(pick_id)
    return None


def _terminal_once_argv() -> Argv:
    strategy = input("Strategy id [sma_cross]: ").strip() or "sma_cross"
    return ["terminal", "once", "--strategy", strategy]


def _terminal_replay_argv() -> Argv:
    csv = _prompt_path("OHLC CSV", _default_csv())
    strategy = input("Strategy id [sma_cross]: ").strip() or "sma_cross"
    return ["terminal", "replay", csv, "--strategy", strategy]


MENUS: tuple[MenuGroup, ...] = (
    MenuGroup(
        title="Charts & compare",
        actions=(
            MenuAction("Live multi-market dashboard (PNG)", _live_chart_argv),
            MenuAction("Watch live markets (refresh PNG)", _live_watch_argv),
            MenuAction("Compare all strategies", _compare_argv),
            MenuAction("Compare with recent-price filters", _compare_argv_filtered),
            MenuAction(
                "Compare BTC 1h (preset)",
                [
                    "strategy",
                    "compare",
                    "data/crypto/ohlc/BTCIRT_60.csv",
                    "--out",
                    "results/strategies/compare/BTCIRT_60",
                    "--visualize",
                ],
            ),
            MenuAction(
                "Compare with vectorbt",
                lambda: [
                    "strategy",
                    "compare",
                    _prompt_path("OHLC CSV", _default_csv()),
                    "--out",
                    _prompt_path("Output dir", "results/strategies/compare/vbt_run"),
                    "--visualize",
                    "--vectorbt",
                ],
            ),
            MenuAction(
                "Strategy batch on folder",
                lambda: [
                    "strategy",
                    "batch",
                    _prompt_path("OHLC directory", "data/crypto/ohlc"),
                    "--strategy",
                    input("Strategy id [ema_cross]: ").strip() or "ema_cross",
                    "--out",
                    _prompt_path("Output dir", "results/strategies/batch/ema_cross"),
                    "--visualize",
                ],
            ),
            MenuAction("Single strategy backtest charts", _strategy_backtest_viz_argv),
            MenuAction("ML forecast: train & eval one dataset", _ml_run_argv),
            MenuAction("ML batch charts (folder)", _ml_batch_viz_argv),
            MenuAction("Browse saved results", _view_saved_results_argv),
            MenuAction("Visualization pickable workflow", _pick_visualization_workflow),
        ),
    ),
    MenuGroup(
        title="Markets & crypto assets",
        actions=(
            MenuAction("List crypto markets (five-source jobs)", ["data", "markets"]),
            MenuAction(
                "List crypto markets (1h jobs file)",
                ["data", "markets", "--jobs", "export.jobs.crypto-1h.json"],
            ),
            MenuAction(
                "Export all crypto markets (1h)",
                [
                    "export",
                    "--jobs",
                    "export.jobs.crypto-1h.json",
                    "--out",
                    "data/crypto",
                ],
            ),
            MenuAction(
                "Compare all strategies on every crypto 1h CSV",
                lambda: _run_pickable_workflow("workflow/compare-all-strategies-crypto-1h"),
            ),
            MenuAction(
                "Crypto 1h local test (all assets, full OHLC, no download)",
                lambda: _run_pickable_workflow("workflow/crypto-1h-local-research"),
            ),
            MenuAction(
                "Run experiment from config (crypto 1h full)",
                ["pipeline", "run-config", "config/experiment.crypto-1h-local.json"],
            ),
            MenuAction(
                "Run experiment from config (crypto 1h smoke)",
                ["pipeline", "run-config", "config/experiment.crypto-1h-smoke.json"],
            ),
            MenuAction(
                "Run ML forecast eval (BTC 1h, test steps + training samples)",
                ["pipeline", "run-config", "config/experiment.ml-forecast-eval.json"],
            ),
        ),
    ),
    MenuGroup(
        title="Data & download",
        actions=(
            MenuAction("List supported markets", ["data", "markets"]),
            MenuAction("Export BTC 1h history", _export_btc_argv),
            MenuAction("Rebuild crypto horizon slices", ["data", "horizons", "--from", "data/crypto/ohlc"]),
        ),
    ),
    MenuGroup(
        title="Strategies & backtests",
        actions=(
            MenuAction("Strategy catalog (implemented)", ["strategy", "catalog", "--implemented-only"]),
            MenuAction(
                "Single backtest (SMA cross)",
                lambda: [
                    "backtest",
                    _prompt_path("OHLC CSV", _default_csv()),
                    "--strategy",
                    "sma_cross",
                    "--out",
                    _prompt_path("Output dir", "results/strategies/backtest/btc_sma_cross"),
                    "--visualize",
                ],
            ),
        ),
    ),
    MenuGroup(
        title="Machine learning",
        actions=(
            MenuAction("Model catalog (implemented)", ["ml", "catalog", "--implemented-only"]),
            MenuAction("LightGBM forecast: train & eval one dataset", _ml_run_argv),
            MenuAction(
                "Batch LightGBM (4h horizon folder)",
                [
                    "ml",
                    "batch",
                    "data/crypto/horizons/4h",
                    "--model",
                    "lightgbm",
                    "--all-horizons",
                ],
            ),
        ),
    ),
    MenuGroup(
        title="Terminal",
        actions=(
            MenuAction("Once — latest closed candle (paper)", _terminal_once_argv),
            MenuAction("Replay OHLC CSV bar-by-bar (paper)", _terminal_replay_argv),
            MenuAction(
                "Poll UDF (paper, 5 steps smoke)",
                ["terminal", "run", "--strategy", "sma_cross", "--max-steps", "5", "--poll-sec", "10"],
            ),
        ),
    ),
    MenuGroup(
        title="Auth & API keys",
        actions=(
            MenuAction("Verify API key (.env)", ["auth", "check"]),
            MenuAction("Login (email, password, 2FA prompts)", ["auth", "login", "--write-env"]),
            MenuAction("List API keys (session token)", ["auth", "apikeys", "list"]),
            MenuAction(
                "Create API key → .env (READ, 2FA prompt)",
                ["auth", "apikeys", "create", "--permissions", "READ", "--write-env"],
            ),
        ),
    ),
    MenuGroup(
        title="Pipelines",
        actions=(
            MenuAction("List pipelines", ["pipeline", "list"]),
            MenuAction("Run full-research-lightgbm", ["pipeline", "run", "full-research-lightgbm"]),
        ),
    ),
    MenuGroup(
        title="Interface",
        actions=(
            MenuAction("Print interface catalog (JSON)", ["interface", "catalog", "--no-examples"]),
            MenuAction("List pickable workflow ids", ["interface", "list"]),
        ),
    ),
)


def _resolve_argv(action: MenuAction) -> Argv | None:
    if callable(action.argv):
        return action.argv()
    return list(action.argv)


def _run_argv(argv: Argv) -> None:
    from traderbot.cli import main as cli_main

    print(f"\n→ {' '.join(['traderbot', *argv])}\n", file=sys.stderr)
    cli_main(argv)


def _pick_workflow() -> None:
    picks = all_pickables()
    print("\nQuick workflows:\n", file=sys.stderr)
    for i, p in enumerate(picks[:20], start=1):
        print(f"  {i:2}) {p.id} — {p.title}", file=sys.stderr)
    print("  … more: traderbot interface list\n", file=sys.stderr)
    line = input("Number or id (empty=cancel): ").strip()
    if not line:
        return
    if line.isdigit():
        idx = int(line) - 1
        if idx < 0 or idx >= len(picks):
            print("invalid number", file=sys.stderr)
            return
        pick_id = picks[idx].id
    else:
        pick_id = line
    steps = run_pickable(pick_id, dry_run=True)
    if steps:
        print(" ".join(steps[0]), file=sys.stderr)
    confirm = input("Run this? [y/N]: ").strip().lower()
    if confirm in ("y", "yes"):
        run_pickable(pick_id)


def _group_menu(group: MenuGroup) -> None:
    while True:
        print(f"\n── {group.title} ──", file=sys.stderr)
        for i, action in enumerate(group.actions, start=1):
            suffix = f" — {action.hint}" if action.hint else ""
            print(f"  {i}) {action.label}{suffix}", file=sys.stderr)
        print("  0) Back", file=sys.stderr)
        line = input("Choice: ").strip()
        if line in ("0", "b", "back", "q"):
            return
        if not line.isdigit():
            continue
        idx = int(line) - 1
        if idx < 0 or idx >= len(group.actions):
            continue
        argv = _resolve_argv(group.actions[idx])
        if argv is None:
            input("\nPress Enter to continue…")
            continue
        _run_argv(argv)
        input("\nPress Enter to continue…")


def _profile_action() -> None:
    from traderbot.cli.root import _nobitex_keys_configured, _print_profile

    if not _nobitex_keys_configured():
        print("Set NOBITEX_API_* in .env (auth apikeys create --write-env)", file=sys.stderr)
        return
    _print_profile()


def run_interactive_hub() -> None:
    if not sys.stdin.isatty():
        from traderbot.cli.root import _build_root_parser

        _build_root_parser().print_help()
        return

    print("\n traderbot — interactive CLI\n", file=sys.stderr)
    while True:
        print("Menu:", file=sys.stderr)
        for i, group in enumerate(MENUS, start=1):
            print(f"  {i}) {group.title}", file=sys.stderr)
        print(f"  {len(MENUS) + 1}) Quick workflow (pick & run)", file=sys.stderr)
        print(f"  {len(MENUS) + 2}) Nobitex profile (API key)", file=sys.stderr)
        print("  0) Exit", file=sys.stderr)
        line = input("Choose: ").strip()
        if line in ("0", "q", "quit", "exit"):
            print("Bye.", file=sys.stderr)
            return
        if not line.isdigit():
            continue
        n = int(line)
        if 1 <= n <= len(MENUS):
            _group_menu(MENUS[n - 1])
            continue
        if n == len(MENUS) + 1:
            _pick_workflow()
            continue
        if n == len(MENUS) + 2:
            _profile_action()
            input("\nPress Enter to continue…")
