import argparse
import json
import os
import sys
from collections.abc import Callable

from traderbot.auth.envfile import load_env_file

_COMMANDS: dict[str, tuple[str, Callable[[list[str]], None]]] = {}


def _register(name: str, help_text: str, main_fn: Callable[[list[str] | None], None]) -> None:
    def runner(argv: list[str]) -> None:
        main_fn(argv)

    _COMMANDS[name] = (help_text, runner)


def _nobitex_keys_configured() -> bool:
    load_env_file()
    pub = os.environ.get("NOBITEX_API_PUBLIC_KEY", "").strip()
    priv = os.environ.get("NOBITEX_API_PRIVATE_KEY", "").strip()
    return bool(pub and priv)


def _print_profile() -> None:
    from traderbot.nobitex.client import NobitexClient, NobitexClientError

    load_env_file()
    try:
        data = NobitexClient.from_env().request("GET", "/users/profile")
    except NobitexClientError as e:
        print(e, file=sys.stderr)
        if e.body is not None:
            print(json.dumps(e.body, ensure_ascii=False, indent=2), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _build_root_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="traderbot",
        description="Nobitex trading bot utilities (export, backtest, ML, pipelines).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "With no arguments: interactive menu (TTY) or this help. "
            "Same menu: traderbot cli. Non-interactive: traderbot <command> …"
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="command")
    for name, (help_text, _) in sorted(_COMMANDS.items()):
        sub.add_parser(name, help=help_text, add_help=False)
    return parser


def _register_commands() -> None:
    if _COMMANDS:
        return
    from traderbot.cli.auth import main as auth_main
    from traderbot.cli.backtest import main as backtest_main
    from traderbot.cli.data import main as data_main
    from traderbot.cli.interface import main as interface_main
    from traderbot.cli.interactive import main as interactive_main
    from traderbot.cli.ml import main as ml_main
    from traderbot.cli.pipeline import main as pipeline_main
    from traderbot.cli.strategy import main as strategy_main
    from traderbot.cli.terminal import main as terminal_main
    from traderbot.cli.export import main as export_main

    _register("cli", "Interactive menu (data, strategy, ml, auth, …)", interactive_main)
    _register("export", "Download OHLC candles to CSV", export_main)
    _register("auth", "Login, API key create/list, verify .env credentials", auth_main)
    _register("backtest", "Backtest one strategy on a CSV", backtest_main)
    _register("strategy", "Strategy catalog, compare, and batch backtests", strategy_main)
    _register("ml", "Forecast model catalog and batch eval", ml_main)
    _register("pipeline", "Named end-to-end research pipelines", pipeline_main)
    _register("data", "Market list, live UDF charts, and horizon slices", data_main)
    _register(
        "interface",
        "Catalog, list, pick, and run CLI actions (export, ML, strategy, pipelines)",
        interface_main,
    )
    _register("terminal", "Live, once, and CSV replay strategy loops", terminal_main)


def main(argv: list[str] | None = None) -> None:
    _register_commands()
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        if sys.stdin.isatty():
            from traderbot.interactive.menu import run_interactive_hub

            run_interactive_hub()
        else:
            _build_root_parser().print_help()
        return

    if args[0] in ("-h", "--help"):
        _build_root_parser().print_help()
        return

    command = args[0]
    if command not in _COMMANDS:
        parser = _build_root_parser()
        parser.error(f"unknown command {command!r}")

    _, runner = _COMMANDS[command]
    runner(args[1:])
