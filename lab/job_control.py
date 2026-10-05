from __future__ import annotations

import threading

_active_cancel_events: dict[str, threading.Event] = {}


class JobStoppedError(Exception):
    """Raised when a Lab job receives a user stop request."""


def register_job_cancel(job_id: str) -> threading.Event:
    cancel_event = threading.Event()
    _active_cancel_events[job_id] = cancel_event
    return cancel_event


def unregister_job_cancel(job_id: str) -> None:
    _active_cancel_events.pop(job_id, None)


def request_job_cancel(job_id: str) -> bool:
    cancel_event = _active_cancel_events.get(job_id)
    if cancel_event is None:
        return False
    cancel_event.set()
    return True


def job_cancel_requested(job_id: str) -> bool:
    cancel_event = _active_cancel_events.get(job_id)
    return cancel_event is not None and cancel_event.is_set()


def raise_if_job_stopped(job_id: str) -> None:
    if job_cancel_requested(job_id):
        raise JobStoppedError("Stopped by user")
