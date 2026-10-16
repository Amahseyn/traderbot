"""WonderTrader integration CLI (backtest + live readiness)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="WonderTrader: smoke tests, full backtest experiment, live readiness"
    )
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("check", help="Print wondertrader_root and runner availability")

    smoke_p = sub.add_parser("smoke", help="Validate dist layout (no native binary)")
    smoke_p.add_argument("--json-out", default="")

    val_p = sub.add_parser("validate", help="Smoke + optional full WtBtRunner experiment")
    val_p.add_argument("--full", action="store_true", help="Run cta/hft/uft/exec backtests")
    val_p.add_argument("--build", action="store_true", help="cmake build macos_bt before --full")
    val_p.add_argument("--log-file", default="")
    val_p.add_argument("--json-report", default="")
    val_p.add_argument("-v", "--verbose", action="store_true")

    exp_p = sub.add_parser("experiment", help="Run full four-engine backtest experiment")
    exp_p.add_argument("--build", action="store_true")
    exp_p.add_argument("--zero-fees", action="store_true")
    exp_p.add_argument("--log-file", default="")
    exp_p.add_argument("--json-out", default="")

    live_p = sub.add_parser("live", help="Live trading readiness")
    live_sub = live_p.add_subparsers(dest="live_action", required=True)
    live_sub.add_parser("check", help="Config templates + env checklist")

    args = parser.parse_args(argv)

    if args.action == "check":
        from traderbot.integrations.wondertrader.experiment import native_runner_available
        from traderbot.integrations.wondertrader.paths import (
            dist_bt_runner,
            macos_bt_runner,
            wondertrader_root,
        )

        payload = {
            "wondertrader_root": str(wondertrader_root()),
            "dist_bt_runner": str(dist_bt_runner()),
            "macos_bt_runner": str(macos_bt_runner()),
            "native_runner_available": native_runner_available(),
        }
        print(json.dumps(payload, indent=2))
        return

    if args.action == "smoke":
        from traderbot.integrations.wondertrader.experiment import run_smoke_test

        result = run_smoke_test()
        text = json.dumps(result, indent=2)
        if args.json_out:
            Path(args.json_out).write_text(text, encoding="utf-8")
            print(f"wrote {args.json_out}")
        else:
            print(text)
        if not result.get("ok"):
            raise SystemExit(1)
        return

    if args.action == "live":
        from traderbot.integrations.wondertrader.live import live_capabilities_payload

        print(json.dumps(live_capabilities_payload(), indent=2, default=str))
        return

    if args.action == "validate":
        repo = Path(__file__).resolve().parents[1]
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from scripts.validate_wondertrader_platform import main as validate_main

        vargv: list[str] = []
        if args.full:
            vargv.append("--full")
        if args.build:
            vargv.append("--build")
        if args.log_file:
            vargv.extend(["--log-file", args.log_file])
        if args.json_report:
            vargv.extend(["--json-report", args.json_report])
        if args.verbose:
            vargv.append("-v")
        raise SystemExit(validate_main(vargv))

    from traderbot.integrations.wondertrader.experiment import run_full_backtest_experiment
    from traderbot.integrations.wondertrader.logging_config import configure_wondertrader_logging
    from traderbot.integrations.wondertrader.paths import logs_dir

    log_path = Path(args.log_file) if args.log_file else logs_dir() / "experiment_cli.log"
    logger = configure_wondertrader_logging(log_path, verbose=False)

    def log(msg: str) -> None:
        logger.info(msg)

    report = run_full_backtest_experiment(
        build=args.build,
        zero_fees=args.zero_fees,
        pnl_report=True,
        log=log,
        log_file=log_path,
    )
    text = json.dumps(report, indent=2, default=str)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
        print(f"wrote {args.json_out}")
    else:
        print(text)
    if not report.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
