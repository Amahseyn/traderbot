from __future__ import annotations

import argparse
import json
from io import StringIO
from pathlib import Path
from typing import Any

from traderbot.terminal.live import run_live
from traderbot.terminal.once import run_once
from traderbot.terminal.replay import run_replay


def _terminal_namespace(body: dict[str, Any], *, csv_path: str | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        strategy=str(body.get("strategy") or "sma_cross"),
        src=str(body.get("src") or "btc"),
        dst=str(body.get("dst") or "rls"),
        interval=str(body.get("interval") or "60"),
        fast=int(body.get("fast") or 5),
        slow=int(body.get("slow") or 20),
        signal=int(body.get("signal") or 9),
        period=int(body.get("period") or 14),
        oversold=float(body.get("oversold") or 30.0),
        overbought=float(body.get("overbought") or 70.0),
        num_std=float(body.get("num_std") or 2.0),
        price_confirm=bool(body.get("price_confirm")),
        no_auto_fine=bool(body.get("no_auto_fine")),
        fine_csv=body.get("fine_csv"),
        live=bool(body.get("live")),
        no_buy=bool(body.get("no_buy")),
        no_sell=bool(body.get("no_sell")),
        emit_holds=bool(body.get("emit_holds")),
        poll_sec=float(body.get("poll_sec") or 60.0),
        max_steps=body.get("max_steps"),
        csv=Path(csv_path) if csv_path else Path(body.get("csv") or "."),
        max_bars=body.get("max_bars"),
        pace_sec=float(body.get("pace_sec") or 0.0),
        use_optimized_defaults=bool(body.get("use_optimized_defaults", True)),
        paper_initial_cash=body.get("paper_initial_cash"),
        paper_fee_rate=body.get("paper_fee_rate"),
        until_stopped=bool(body.get("until_stopped")),
    )


def _run_terminal_callable(callable_fn) -> None:
    try:
        callable_fn()
    except SystemExit as exc:
        code = exc.code if exc.code is not None else 1
        raise RuntimeError(f"terminal command failed (exit {code})") from exc


def run_terminal_once_task(body: dict[str, Any]) -> None:
    from auth.envfile import load_env_file

    load_env_file()
    args = _terminal_namespace(body)
    buffer = StringIO()
    import sys

    def invoke() -> None:
        old_stdout = sys.stdout
        try:
            sys.stdout = buffer
            run_once(args)
        finally:
            sys.stdout = old_stdout

    _run_terminal_callable(invoke)
    print(buffer.getvalue())


def run_terminal_replay_task(body: dict[str, Any], csv_path: str) -> None:
    args = _terminal_namespace(body, csv_path=csv_path)
    import sys
    from contextlib import redirect_stdout

    buffer = StringIO()
    def invoke() -> None:
        with redirect_stdout(buffer):
            run_replay(args)

    _run_terminal_callable(invoke)
    print(buffer.getvalue())


def run_terminal_live_task(body: dict[str, Any]) -> None:
    from auth.envfile import load_env_file
    from lab.job_control import JobStoppedError, job_cancel_requested

    load_env_file()
    until_stopped = bool(body.get("until_stopped"))
    max_steps = body.get("max_steps")
    if until_stopped:
        max_steps = None
    elif max_steps is None:
        max_steps = 5
    else:
        max_steps = int(max_steps)
    body = {**body, "max_steps": max_steps, "until_stopped": until_stopped}
    job_id = body.get("job_id")
    args = _terminal_namespace(body)
    if isinstance(job_id, str) and job_id:

        def should_stop() -> bool:
            if job_cancel_requested(job_id):
                raise JobStoppedError("Stopped by user")
            return False

        args.should_stop = should_stop
    print(
        json.dumps(
            {
                "terminal": "live",
                "symbol": f"{args.src}/{args.dst}",
                "interval": args.interval,
                "strategy": args.strategy,
                "max_steps": args.max_steps,
                "poll_sec": args.poll_sec,
            },
        ),
        flush=True,
    )
    _run_terminal_callable(lambda: run_live(args))
