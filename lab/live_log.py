from __future__ import annotations

import json
import math
from typing import Any


def parse_json_log_lines(log_text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in log_text.splitlines():
        trimmed = line.strip()
        if not trimmed.startswith("{"):
            continue
        try:
            row = json.loads(trimmed)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def summarize_live_job_log(log_text: str) -> dict[str, Any]:
    """Parse terminal job logs the same way the Lab live chart UI does."""
    markers: list[dict[str, Any]] = []
    paper_wallet: dict[str, Any] | None = None
    paper_initial_cash: float | None = None
    strategy_ids: list[str] = []
    seen_strategy: set[str] = set()
    terminal_banner: dict[str, Any] | None = None
    live_tune_events: list[dict[str, Any]] = []
    live_tune_start_events: list[dict[str, Any]] = []
    live_tune_complete_events: list[dict[str, Any]] = []
    live_exchange_events: list[dict[str, Any]] = []
    has_signal_activity = False

    for row in parse_json_log_lines(log_text):
        event = row.get("event")
        if event in ("signal", "once", "tick"):
            has_signal_activity = True
        strategy_raw = row.get("strategy_id") or row.get("strategy")
        if isinstance(strategy_raw, str) and strategy_raw.strip():
            key = strategy_raw.strip()
            if key not in seen_strategy:
                seen_strategy.add(key)
                strategy_ids.append(key)

        if event == "paper_wallet" and isinstance(row.get("initial_cash"), (int, float)):
            paper_initial_cash = float(row["initial_cash"])

        portfolio = row.get("portfolio")
        if isinstance(portfolio, dict):
            paper_wallet = dict(portfolio)

        if event in ("signal", "once"):
            action = row.get("action")
            if action in ("buy", "sell"):
                timestamp = row.get("timestamp", row.get("bar_timestamp"))
                close = row.get("close")
                try:
                    ts = float(timestamp)
                    price = float(close)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(ts) or not math.isfinite(price):
                    continue
                markers.append(
                        {
                            "timestamp": int(ts) if ts == int(ts) else ts,
                            "action": action,
                            "price": price,
                            "mode": row.get("mode"),
                            "strategy_id": strategy_raw,
                        }
                    )

        if row.get("terminal") in ("live", "once"):
            terminal_banner = dict(row)

        if event == "live_tune_sweep":
            live_tune_events.append(dict(row))
        if event == "live_tune_start":
            live_tune_start_events.append(dict(row))
        if event == "live_tune_complete":
            live_tune_complete_events.append(dict(row))
        if event == "live_exchange":
            live_exchange_events.append(dict(row))

    phases: list[str] = []
    if live_tune_start_events:
        phases.append("optimize")
    if live_tune_events:
        phases.append("optimize_result")
    if live_tune_complete_events:
        phases.append("optimize_done")
    if terminal_banner:
        phases.append(f"terminal_{terminal_banner.get('terminal', 'session')}")
    if markers or has_signal_activity:
        phases.append("signals")

    return {
        "markers": markers,
        "paper_wallet": paper_wallet,
        "paper_initial_cash": paper_initial_cash,
        "strategy_ids": strategy_ids,
        "terminal_banner": terminal_banner,
        "live_tune_events": live_tune_events,
        "live_tune_start_events": live_tune_start_events,
        "live_tune_complete_events": live_tune_complete_events,
        "live_exchange_events": live_exchange_events,
        "phases": phases,
    }


def assert_log_contains_strategy(log_text: str, strategy_id: str) -> None:
    summary = summarize_live_job_log(log_text)
    if strategy_id not in summary["strategy_ids"]:
        raise AssertionError(
            f"log missing strategy_id {strategy_id!r}; found {summary['strategy_ids']!r}",
        )
