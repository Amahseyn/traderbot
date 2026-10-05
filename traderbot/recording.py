from __future__ import annotations

from typing import Any, Callable

Recorder = Callable[..., None]

_recorder: Recorder | None = None


def set_recorder(recorder: Recorder | None) -> None:
    global _recorder
    _recorder = recorder


def try_record(kind: str, **payload: Any) -> None:
    if _recorder is None:
        return
    _recorder(kind, **payload)
