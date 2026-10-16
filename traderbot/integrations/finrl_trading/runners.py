"""Invoke FinRL-Trading scripts (equity / ML / deploy)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from traderbot.integrations.finrl_trading.paths import finrl_trading_root


def _run_finrl_script(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    root = finrl_trading_root()
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd or root,
        capture_output=True,
        text=True,
    )


def run_finrl_deploy_adaptive_rotation(
    *,
    start: str = "2023-01-01",
    end: str = "2024-12-31",
    skip_download: bool = True,
) -> dict[str, Any]:
    root = finrl_trading_root()
    deploy = root / "deploy.sh"
    if not deploy.is_file():
        raise FileNotFoundError(deploy)
    cmd = [
        "bash",
        str(deploy),
        "--strategy",
        "adaptive_rotation",
        "--mode",
        "backtest",
        "--start",
        start,
        "--end",
        end,
    ]
    if skip_download:
        cmd.append("--skip-download")
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:] if proc.stdout else "",
        "stderr": proc.stderr[-4000:] if proc.stderr else "",
        "ok": proc.returncode == 0,
    }


def run_finrl_hyperliquid_research_validate(
    *,
    src: str = "btc",
    intervals: str = "1",
    max_bars: int = 100,
) -> dict[str, Any]:
    root = finrl_trading_root()
    script = root.parent / "traderbot" / "scripts" / "validate_hyperliquid_research.py"
    if not script.is_file():
        script = Path(__file__).resolve().parents[3] / "scripts" / "validate_hyperliquid_research.py"
    if not script.is_file():
        return {"skipped": True, "reason": "validate_hyperliquid_research.py not found"}
    proc = subprocess.run(
        [
            sys.executable,
            str(script),
            "--src",
            src,
            "--intervals",
            intervals,
            "--max-bars",
            str(max_bars),
        ],
        cwd=script.parent.parent,
        capture_output=True,
        text=True,
    )
    return {
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "stdout_tail": (proc.stdout or "")[-6000:],
        "stderr_tail": (proc.stderr or "")[-3000:],
    }
