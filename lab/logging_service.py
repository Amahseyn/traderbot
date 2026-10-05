"""
Comprehensive Logging System for Traderbot Lab.

Features:
- Centralized log collection (all modules)
- Real-time streaming via WebSocket
- Filtering by level, module, timestamp
- Persistent storage in SQLite
- Performance metrics
"""

from __future__ import annotations

import io
import json
import logging
import logging.handlers
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

__all__ = [
    "LogLevel",
    "LogEntry",
    "LogCollector",
    "setup_logging",
]


class LogLevel(str, Enum):
    """Standard logging levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @classmethod
    def from_logging_level(cls, level: int) -> LogLevel:
        """Convert logging module level to our enum."""
        level_map = {
            logging.DEBUG: cls.DEBUG,
            logging.INFO: cls.INFO,
            logging.WARNING: cls.WARNING,
            logging.ERROR: cls.ERROR,
            logging.CRITICAL: cls.CRITICAL,
        }
        return level_map.get(level, cls.INFO)


@dataclass
class LogEntry:
    """Single log entry with metadata."""

    timestamp: float = field(default_factory=time.time)
    level: str = "INFO"
    module: str = ""
    message: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    source: str = "app"  # 'app', 'job', 'api', etc.

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @property
    def timestamp_iso(self) -> str:
        """ISO format timestamp."""
        return datetime.utcfromtimestamp(self.timestamp).isoformat() + "Z"


class LogCollector:
    """
    Centralized log collection from all modules.

    Features:
    - In-memory circular buffer
    - Optional persistent storage
    - Filtering and search
    - Real-time subscribers
    """

    def __init__(self, max_entries: int = 100000):
        self._entries: list[LogEntry] = []
        self._max_entries = max_entries
        self._subscribers: list[Callable[[LogEntry], None]] = []
        self._filters: dict[str, set[str]] = {
            "level": set(),
            "module": set(),
            "source": set(),
        }

    def add(self, entry: LogEntry) -> None:
        """Add log entry (internal use; use logging module instead)."""
        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

        # Notify subscribers
        for subscriber in self._subscribers:
            try:
                subscriber(entry)
            except Exception as e:
                logging.exception(f"Error notifying subscriber: {e}")

    def subscribe(self, callback: Callable[[LogEntry], None]) -> Callable[[], None]:
        """Subscribe to new log entries. Returns unsubscribe function."""
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            self._subscribers.remove(callback)

        return unsubscribe

    def get_recent(
        self,
        limit: int = 100,
        level: str | None = None,
        module: str | None = None,
        source: str | None = None,
        since_timestamp: float | None = None,
    ) -> list[LogEntry]:
        """Retrieve logs with optional filtering."""
        result = self._entries

        # Filter by timestamp
        if since_timestamp is not None:
            result = [e for e in result if e.timestamp >= since_timestamp]

        # Filter by level
        if level is not None:
            result = [e for e in result if e.level == level]

        # Filter by module
        if module is not None:
            result = [e for e in result if module in e.module]

        # Filter by source
        if source is not None:
            result = [e for e in result if e.source == source]

        # Return latest N
        return result[-limit:]

    def search(self, query: str, limit: int = 100) -> list[LogEntry]:
        """Full-text search in log messages."""
        query_lower = query.lower()
        results = [e for e in self._entries if query_lower in e.message.lower()]
        return results[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Log statistics."""
        if not self._entries:
            return {"total": 0}

        levels = {}
        modules = set()
        sources = set()

        for entry in self._entries:
            levels[entry.level] = levels.get(entry.level, 0) + 1
            modules.add(entry.module)
            sources.add(entry.source)

        oldest = self._entries[0].timestamp
        newest = self._entries[-1].timestamp

        return {
            "total": len(self._entries),
            "by_level": levels,
            "unique_modules": len(modules),
            "unique_sources": len(sources),
            "time_span_seconds": newest - oldest,
            "oldest_timestamp": oldest,
            "newest_timestamp": newest,
        }


def _skip_lab_log_record(record: logging.LogRecord) -> bool:
    """Drop noisy HTTP access lines from the Lab log UI."""
    if record.name == "uvicorn.access":
        return True
    message = record.getMessage()
    if '"GET /' in message or '"POST /' in message or '"PUT /' in message:
        if "HTTP/1.1" in message and "127.0.0.1" in message:
            return True
    return False


class LabLoggingHandler(logging.Handler):
    """Custom logging handler that feeds into LogCollector."""

    def __init__(self, collector: LogCollector, source: str = "app"):
        super().__init__()
        self.collector = collector
        self.source = source

    def emit(self, record: logging.LogRecord) -> None:
        """Handle log record."""
        if _skip_lab_log_record(record):
            return
        try:
            entry = LogEntry(
                timestamp=record.created,
                level=LogLevel.from_logging_level(record.levelno).value,
                module=record.name,
                message=record.getMessage(),
                context={
                    "pathname": record.pathname,
                    "lineno": record.lineno,
                    "funcName": record.funcName,
                    "process": record.process,
                },
                source=self.source,
            )
            self.collector.add(entry)
        except Exception:
            self.handleError(record)


def setup_logging(
    collector: LogCollector,
    level: int = logging.INFO,
    source: str = "app",
    log_file: Path | None = None,
) -> None:
    """
    Configure Python logging to use LogCollector.

    Args:
        collector: LogCollector instance to feed logs into
        level: Logging level (logging.DEBUG, INFO, etc.)
        source: Source identifier for this logger
        log_file: Optional file to also write logs to
    """
    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Lab handler (feeds into collector)
    lab_handler = LabLoggingHandler(collector, source=source)
    lab_handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    lab_handler.setFormatter(formatter)
    root_logger.addHandler(lab_handler)

    # Optional file handler
    if log_file is not None:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


__all__ += [
    "LabLoggingHandler",
    "setup_logging",
]
