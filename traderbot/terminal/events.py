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
    event: str = "signal",
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
    return payload


def print_signal_event(
    action: SignalAction,
    bar: Bar,
    *,
    mode: str,
    strategy_id: str | None = None,
    emit_holds: bool = False,
) -> None:
    if action == "hold" and not emit_holds:
        return
    print(json.dumps(signal_event_dict(action, bar, mode=mode, strategy_id=strategy_id), ensure_ascii=False))
