#!/usr/bin/env python3
"""
WonderTrader platform validation for traderbot monorepo layout.

  python scripts/validate_wondertrader_platform.py
  python scripts/validate_wondertrader_platform.py --full --build
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from traderbot.integrations.wondertrader.logging_config import configure_wondertrader_logging
from traderbot.integrations.wondertrader.paths import logs_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate WonderTrader integration")
    parser.add_argument("--full", action="store_true", help="Run WtBtRunner four-engine experiment")
    parser.add_argument("--build", action="store_true", help="Build macos_bt when running --full")
    parser.add_argument("--log-file", default="")
    parser.add_argument("--json-report", default="")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    log_file = Path(args.log_file) if args.log_file else logs_dir() / "validate_platform.log"
    logger = configure_wondertrader_logging(log_file, verbose=args.verbose)

    from traderbot.integrations.wondertrader.experiment import run_platform_validation

    report = run_platform_validation(
        full_backtest=args.full,
        build=args.build,
        log=lambda m: logger.info("%s", m),
        log_file=log_file,
    )

    if args.json_report:
        out = Path(args.json_report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        logger.info("wrote %s", out)
    else:
        print(json.dumps(report, indent=2, default=str))

    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
