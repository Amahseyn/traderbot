"""FinRL-Trading integration CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run traderbot + FinRL-Trading platform experiment")
    sub = parser.add_subparsers(dest="action", required=True)

    run_p = sub.add_parser("run", help="Full HL export + FinRL intraday + traderbot backtest")
    run_p.add_argument("--src", default="btc")
    run_p.add_argument("--dst", default="usdt")
    run_p.add_argument("--intervals", default="1,5")
    run_p.add_argument("--max-bars", type=int, default=100)
    run_p.add_argument("--equity-periods", type=int, default=100)
    run_p.add_argument("--no-equity-rotation", action="store_true")
    run_p.add_argument("--no-strategy-compare", action="store_true")
    run_p.add_argument("--algo-sweep", action="store_true", help="Run HL validate_hyperliquid_research (all strategies)")
    run_p.add_argument("--deploy-backtest", action="store_true", help="Run FinRL deploy.sh adaptive_rotation backtest")
    run_p.add_argument("--json-out", type=str, default="")

    sub.add_parser("check", help="Verify FinRL-Trading path and shared env")

    val_p = sub.add_parser("validate", help="Leakage checks + walk-forward validate on live HL export")
    val_p.add_argument("--src", default="btc")
    val_p.add_argument("--interval", default="1")
    val_p.add_argument("--max-bars", type=int, default=200)
    val_p.add_argument("--log-file", type=str, default="")
    val_p.add_argument("--json-report", type=str, default="")
    val_p.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args(argv)

    if args.action == "check":
        from traderbot.integrations.finrl_trading.env import load_shared_env
        from traderbot.integrations.finrl_trading.paths import finrl_trading_root, traderbot_root

        env_files = load_shared_env()
        print(
            json.dumps(
                {
                    "traderbot_root": str(traderbot_root()),
                    "finrl_trading_root": str(finrl_trading_root()),
                    "env_files": [str(p) for p in env_files],
                },
                indent=2,
            )
        )
        return

    if args.action == "validate":
        repo = Path(__file__).resolve().parents[1]
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from scripts.validate_finrl_platform import main as validate_main

        vargv = [
            "--src",
            args.src,
            "--interval",
            str(args.interval),
            "--max-bars",
            str(args.max_bars),
        ]
        if args.log_file:
            vargv.extend(["--log-file", args.log_file])
        if args.json_report:
            vargv.extend(["--json-report", args.json_report])
        if args.verbose:
            vargv.append("-v")
        raise SystemExit(validate_main(vargv))

    from traderbot.integrations.finrl_trading.research import run_full_platform_experiment

    from traderbot.hyperliquid.market_data import hyperliquid_resolution

    intervals = [hyperliquid_resolution(p.strip()) for p in args.intervals.split(",") if p.strip()]
    report = run_full_platform_experiment(
        src=args.src,
        dst=args.dst,
        intervals=intervals,
        max_bars=args.max_bars,
        equity_periods=args.equity_periods,
        include_equity_rotation=not args.no_equity_rotation,
        include_strategy_compare=not args.no_strategy_compare,
        include_hyperliquid_algo_sweep=args.algo_sweep,
        include_deploy_backtest=args.deploy_backtest,
    )
    text = json.dumps(report, indent=2, default=str)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
        print(f"wrote {args.json_out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
