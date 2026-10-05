from __future__ import annotations

import sys
from typing import Any

from lab.store.enabled import store_recording_enabled


def try_record(label: str, callback) -> None:
    if not store_recording_enabled():
        return
    try:
        callback()
    except Exception as exc:
        print(f"traderbot store: {label} failed: {exc}", file=sys.stderr)
