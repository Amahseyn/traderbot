from __future__ import annotations

import json
from typing import Any

from traderbot.algorithms.base import Bar, SignalAction


def signal_event_dict(
    action: SignalAction,
    bar: Bar,
    *,
    mode: str,
    strategy_id: str | None = None,
    event = "signal",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "event": event,
        "mode": mode,
        "action": action,
        "timestamp": bar.get("timestamp"),
        "close": bar.get("close"),
        "symbol": bar.get("symbol"),
    }
    if strategy_id is not None:
        payload["strategy_id"] = strategy_id
    if extra:
        payload.update(extra)
    return payload


def print_signal_event(
    action: SignalAction,
    bar: Bar,
    *,
    mode: str,
    strategy_id: str | None = None,
    emit_holds = False,
    extra: dict[str, Any] | None = None,
) -> None:
    if action == "hold" and not emit_holds:
        return
    print(
        json.dumps(
            signal_event_dict(action, bar, mode=mode, strategy_id=strategy_id, extra=extra),
            ensure_ascii=False,
        ),
        flush=True,
    )


def print_tick_event(payload: dict[str, Any]) -> None:
    """One JSON line per live poll (heartbeat / evaluation without a trade)."""
    print(json.dumps(payload, ensure_ascii=False), flush=True)
