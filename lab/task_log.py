from __future__ import annotations

import io
import time
import threading
from collections.abc import Callable

from lab.job_control import JobStoppedError

JOB_LOG_FLUSH_SECONDS = 0.25
JOB_LOG_MAX_CHARS = 400_000


def _set_job_log(connection, job_id: str, log_text: str) -> None:
    if len(log_text) > JOB_LOG_MAX_CHARS:
        log_text = log_text[-JOB_LOG_MAX_CHARS:]
    connection.execute(
        "UPDATE jobs SET log_text = ? WHERE id = ?",
        (log_text, job_id),
    )
    connection.commit()


class JobLogWriter(io.TextIOBase):
    """Captures stdout/stderr from in-process Lab tasks and flushes to SQLite."""

    def __init__(self, connection_factory: Callable, job_id: str) -> None:
        self._connection_factory = connection_factory
        self._job_id = job_id
        self._parts: list[str] = []
        self._last_flush = time.monotonic()

    def write(self, text: str) -> int:
        if not text:
            return 0
        self._parts.append(text)
        if len("".join(self._parts)) > JOB_LOG_MAX_CHARS:
            joined = "".join(self._parts)
            self._parts = [joined[-JOB_LOG_MAX_CHARS:]]
        now = time.monotonic()
        if now - self._last_flush >= JOB_LOG_FLUSH_SECONDS:
            self._flush_db()
        return len(text)

    def flush(self) -> None:
        self._flush_db()

    def _flush_db(self) -> None:
        if not self._parts:
            return
        connection = self._connection_factory()
        try:
            _set_job_log(connection, self._job_id, "".join(self._parts))
        finally:
            connection.close()
        self._last_flush = time.monotonic()

    def getvalue(self) -> str:
        return "".join(self._parts)


class CancellableJobLogWriter(JobLogWriter):
    """Job log writer that raises when the user requests a stop."""

    def __init__(
        self,
        connection_factory: Callable,
        job_id: str,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__(connection_factory, job_id)
        self._cancel_event = cancel_event

    def write(self, text: str) -> int:
        if self._cancel_event.is_set():
            raise JobStoppedError("Stopped by user")
        return super().write(text)

    def flush(self) -> None:
        if self._cancel_event.is_set():
            raise JobStoppedError("Stopped by user")
        super().flush()
