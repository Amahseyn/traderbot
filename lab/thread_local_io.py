from __future__ import annotations

import io
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO

_installed = False
_stdout_proxy: ThreadLocalTextIO | None = None
_stderr_proxy: ThreadLocalTextIO | None = None


class ThreadLocalTextIO(io.TextIOBase):
    """Routes writes to a per-thread stack of writers; falls back to the real stream."""

    def __init__(self, fallback: TextIO) -> None:
        self._fallback = fallback
        self._local = threading.local()

    def _stack(self) -> list[TextIO]:
        stack = getattr(self._local, "stack", None)
        if stack is None:
            stack = []
            self._local.stack = stack
        return stack

    def _target(self) -> TextIO:
        stack = self._stack()
        if stack:
            return stack[-1]
        return self._fallback

    @contextmanager
    def bind(self, writer: TextIO) -> Iterator[None]:
        self._stack().append(writer)
        try:
            yield
        finally:
            stack = self._stack()
            if stack:
                stack.pop()

    def write(self, text: str) -> int:
        if not text:
            return 0
        return self._target().write(text)

    def flush(self) -> None:
        self._target().flush()

    def writable(self) -> bool:
        return True

    @property
    def encoding(self) -> str:
        return getattr(self._target(), "encoding", "utf-8")

    @property
    def errors(self) -> str | None:
        return getattr(self._target(), "errors", None)

    def isatty(self) -> bool:
        return self._target().isatty()

    def fileno(self) -> int:
        return self._target().fileno()


def ensure_thread_local_streams() -> None:
    """Install process-wide stdout/stderr proxies (safe for concurrent Lab jobs)."""
    global _installed, _stdout_proxy, _stderr_proxy
    if not _installed:
        _stdout_proxy = ThreadLocalTextIO(sys.__stdout__)
        _stderr_proxy = ThreadLocalTextIO(sys.__stderr__)
        _installed = True
    # Re-attach after frameworks (e.g. pytest) replace sys.stdout between tests.
    if sys.stdout is not _stdout_proxy:
        sys.stdout = _stdout_proxy
    if sys.stderr is not _stderr_proxy:
        sys.stderr = _stderr_proxy


@contextmanager
def bind_job_output(writer: TextIO) -> Iterator[None]:
    """Capture this thread's stdout/stderr into writer without affecting other threads."""
    ensure_thread_local_streams()
    assert _stdout_proxy is not None and _stderr_proxy is not None
    with _stdout_proxy.bind(writer), _stderr_proxy.bind(writer):
        yield
