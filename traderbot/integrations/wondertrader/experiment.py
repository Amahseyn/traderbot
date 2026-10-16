from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from traderbot.integrations.wondertrader.paths import (
    logs_dir,
    macos_bt_runner,
    wondertrader_root,
)

LogFn = Callable[[str], None]


def _default_log(msg: str) -> None:
    print(msg, flush=True)


def run_smoke_test(log: LogFn | None = None) -> dict[str, Any]:
    log = log or _default_log
    root = wondertrader_root()
    script = root / "scripts" / "smoke_test_dist.py"
    if not script.is_file():
        raise FileNotFoundError(script)
    log(f"smoke: {script}")
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=root,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 0
    if not ok:
        log(out[-4000:])
    return {"ok": ok, "exit_code": proc.returncode, "output_tail": out.strip()[-2000:]}


def native_runner_available() -> bool:
    import platform

    if platform.system() == "Darwin":
        return macos_bt_runner().is_file()
    root = wondertrader_root()
    return (root / "dist" / "WtBtRunner" / "WtBtRunner.exe").is_file()


def run_full_backtest_experiment(
    *,
    build: bool = False,
    zero_fees: bool = False,
    pnl_report: bool = True,
    log: LogFn | None = None,
    log_file: Path | None = None,
) -> dict[str, Any]:
    """Run wondertrader/scripts/run_full_experiment.py (cta/hft/uft/exec)."""
    log = log or _default_log
    root = wondertrader_root()
    script = root / "scripts" / "run_full_experiment.py"
    if not script.is_file():
        raise FileNotFoundError(script)

    if log_file is None:
        log_file = logs_dir() / "backtest_experiment.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    argv = [sys.executable, str(script), "--log-file", str(log_file)]
    if build:
        argv.append("--build")
    if zero_fees:
        argv.append("--zero-fees")
    if pnl_report:
        argv.append("--pnl-report")

    log(f"experiment: {' '.join(argv)}")
    proc = subprocess.run(argv, cwd=root, capture_output=True, text=True)
    combined = (proc.stdout or "") + (proc.stderr or "")
    if combined.strip():
        log(combined.strip()[-3000:])

    manifest_path = root / "experiment_results" / "wondertrader_experiment.json"
    manifest: dict[str, Any] = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    ok = proc.returncode == 0 and all(r.get("ok") for r in manifest.get("runs", []))
    return {
        "ok": ok,
        "exit_code": proc.returncode,
        "manifest_path": str(manifest_path),
        "log_file": str(log_file),
        "manifest": manifest,
        "runner_built": native_runner_available(),
    }


def run_platform_validation(
    *,
    full_backtest: bool = False,
    build: bool = False,
    log: LogFn | None = None,
    log_file: Path | None = None,
) -> dict[str, Any]:
    logger = logging.getLogger("traderbot.wondertrader")
    log = log or (lambda m: logger.info("%s", m))

    report: dict[str, Any] = {
        "wondertrader_root": str(wondertrader_root()),
        "smoke": None,
        "backtest": None,
        "live": None,
        "ok": False,
    }

    report["smoke"] = run_smoke_test(log=log)
    from traderbot.integrations.wondertrader.live import assess_live_readiness

    report["live"] = assess_live_readiness()

    if full_backtest:
        if not build and not native_runner_available():
            report["backtest"] = {
                "ok": False,
                "skipped": True,
                "reason": "WtBtRunner not built; pass build=True or run scripts/build_macos_bt.sh",
            }
        else:
            report["backtest"] = run_full_backtest_experiment(
                build=build,
                pnl_report=True,
                log=log,
                log_file=log_file,
            )

    smoke_ok = bool(report["smoke"] and report["smoke"].get("ok"))
    bt = report.get("backtest")
    bt_ok = bt is None or bt.get("skipped") or bt.get("ok")
    report["ok"] = smoke_ok and bt_ok
    return report
