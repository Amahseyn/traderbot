import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path

_COMMANDS: dict[str, tuple[str, Callable[[list[str]], None]]] = {}


def _register(name: str, help_text: str, main_fn: Callable[[list[str] | None], None]) -> None:
    def runner(argv: list[str]) -> None:
        main_fn(argv)

    _COMMANDS[name] = (help_text, runner)


def _load_dotenv(path: Path | None = None) -> None:
    path = path or Path.cwd() / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _print_profile() -> None:
    from traderbot.client import NobitexClient, NobitexClientError

    _load_dotenv()
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
        epilog="Run `traderbot` with no arguments to print your Nobitex profile (.env keys required).",
    )
    sub = parser.add_subparsers(dest="command", metavar="command")
    for name, (help_text, _) in sorted(_COMMANDS.items()):
        sub.add_parser(name, help=help_text, add_help=False)
    return parser


def _register_commands() -> None:
    if _COMMANDS:
        return
    from traderbot.backtest_cli import main as backtest_main
    from traderbot.data_cli import main as data_main
    from traderbot.export_csv import main as export_main
    from traderbot.ml_cli import main as ml_main
    from traderbot.pipeline_cli import main as pipeline_main
    from traderbot.strategy_cli import main as strategy_main

    _register("export", "Download OHLC candles to CSV", export_main)
    _register("backtest", "Backtest one strategy on a CSV", backtest_main)
    _register("strategy", "Strategy catalog, compare, and batch backtests", strategy_main)
    _register("ml", "Forecast model catalog and batch eval", ml_main)
    _register("pipeline", "Named end-to-end research pipelines", pipeline_main)
    _register("data", "Rebuild crypto horizon slices on disk", data_main)


def main(argv: list[str] | None = None) -> None:
    _register_commands()
    args = list(sys.argv[1:] if argv is None else argv)

    if not args:
        _print_profile()
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
