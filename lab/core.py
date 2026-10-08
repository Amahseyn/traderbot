"""
Traderbot Lab Core Architecture — Scalable, modular, extensible.

This module defines the foundational abstractions for the Lab system:
- ServiceRegistry: Dependency injection and service discovery
- EventBus: Decoupled event-driven communication
- CacheLayer: Multi-level caching (in-process, Redis optional)
- MetricsCollector: Built-in observability for scaling
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, Protocol, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
E = TypeVar("E")


class EventType(str, Enum):
    """Core Lab events — emit when state changes."""

    JOB_QUEUED = "job_queued"
    JOB_STARTED = "job_started"
    JOB_COMPLETED = "job_completed"
    JOB_FAILED = "job_failed"
    RUN_RECORDED = "run_recorded"
    EXPERIMENT_COMPLETED = "experiment_completed"
    DATASET_CACHED = "dataset_cached"


@dataclass
class LabEvent:
    """Universal event object for pub/sub."""

    event_type: EventType
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "source": self.source,
            "payload": self.payload,
        }


class EventSubscriber(Protocol):
    """Protocol for event listeners."""

    def on_event(self, event: LabEvent) -> None:
        """Handle incoming event."""
        ...


class EventBus:
    """Decoupled pub/sub for Lab components."""

    def __init__(self):
        self._subscribers: dict[EventType, list[EventSubscriber]] = defaultdict(list)
        self._event_log: list[LabEvent] = []
        self._max_log_size = 10000

    def subscribe(self, event_type: EventType, subscriber: EventSubscriber) -> Callable[[], None]:
        """Subscribe to event type. Returns unsubscribe function."""
        self._subscribers[event_type].append(subscriber)

        def unsubscribe() -> None:
            self._subscribers[event_type].remove(subscriber)

        return unsubscribe

    def emit(self, event: LabEvent) -> None:
        """Emit event to all subscribers."""
        self._event_log.append(event)
        if len(self._event_log) > self._max_log_size:
            self._event_log = self._event_log[-self._max_log_size :]

        for subscriber in self._subscribers[event.event_type]:
            try:
                subscriber.on_event(event)
            except Exception as e:
                logger.exception(f"Error in event handler: {e}")

    def get_event_log(self, event_type: EventType | None = None) -> list[LabEvent]:
        """Retrieve recent events (for debugging, streaming to UI)."""
        if event_type is None:
            return self._event_log.copy()
        return [e for e in self._event_log if e.event_type == event_type]


@dataclass
class CacheEntry(Generic[T]):
    """Cached value with TTL and metadata."""

    value: T
    created_at: float = field(default_factory=time.time)
    ttl_seconds: int = 3600
    hits: int = 0
    source: str = "unknown"

    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds

    def record_hit(self) -> None:
        self.hits += 1


class CacheLayer:
    """Multi-level cache: in-process + optional Redis backend."""

    def __init__(self, redis_url: str | None = None):
        self._memory_cache: dict[str, CacheEntry] = {}
        self._redis_url = redis_url
        self._redis = None
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def get(self, key: str) -> Any | None:
        """Retrieve from cache (memory first, then Redis)."""
        # Try memory
        if key in self._memory_cache:
            entry = self._memory_cache[key]
            if not entry.is_expired():
                entry.record_hit()
                self._stats["hits"] += 1
                return entry.value
            else:
                del self._memory_cache[key]

        # Try Redis (if configured)
        if self._redis_url:
            try:
                import redis

                if self._redis is None:
                    self._redis = redis.from_url(self._redis_url)
                val = self._redis.get(key)
                if val:
                    self._stats["hits"] += 1
                    return json.loads(val)
            except Exception as e:
                logger.debug(f"Redis cache miss: {e}")

        self._stats["misses"] += 1
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 3600, source: str = "unknown") -> None:
        """Store in cache (both memory and Redis if configured)."""
        entry = CacheEntry(value=value, ttl_seconds=ttl_seconds, source=source)
        self._memory_cache[key] = entry

        if self._redis_url:
            try:
                import redis

                if self._redis is None:
                    self._redis = redis.from_url(self._redis_url)
                self._redis.setex(key, ttl_seconds, json.dumps(value))
            except Exception as e:
                logger.debug(f"Redis cache set failed: {e}")

    def invalidate(self, key: str) -> None:
        """Remove from cache."""
        if key in self._memory_cache:
            del self._memory_cache[key]

        if self._redis_url:
            try:
                import redis

                if self._redis is None:
                    self._redis = redis.from_url(self._redis_url)
                self._redis.delete(key)
            except Exception as e:
                logger.debug(f"Redis cache delete failed: {e}")

    def stats(self) -> dict[str, Any]:
        """Cache performance metrics."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total if total > 0 else 0
        return {
            **self._stats,
            "total": total,
            "hit_rate": hit_rate,
            "memory_entries": len(self._memory_cache),
        }


@dataclass
class MetricsPoint:
    """Single metric observation."""

    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }


class MetricsCollector:
    """Built-in observability — track system health, performance, usage."""

    def __init__(self):
        self._metrics: list[MetricsPoint] = []
        self._gauges: dict[str, float] = {}
        self._max_metrics = 50000

    def record(self, name: str, value: float, tags: dict[str, str] | None = None) -> None:
        """Record a metric point."""
        point = MetricsPoint(name=name, value=value, tags=tags or {})
        self._metrics.append(point)
        if len(self._metrics) > self._max_metrics:
            self._metrics = self._metrics[-self._max_metrics :]

    def gauge(self, name: str, value: float) -> None:
        """Set a gauge value (latest wins)."""
        self._gauges[name] = value

    @contextmanager
    def timer(self, name: str, tags: dict[str, str] | None = None):
        """Context manager to time a code block."""
        start = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - start
            self.record(name, elapsed, tags or {})

    def get_metrics(self, since_timestamp: float | None = None) -> list[MetricsPoint]:
        """Retrieve recent metrics (for UI dashboard, alerts)."""
        if since_timestamp is None:
            return self._metrics.copy()
        return [m for m in self._metrics if m.timestamp >= since_timestamp]

    def get_gauges(self) -> dict[str, float]:
        """Get current gauge values."""
        return self._gauges.copy()

    def summary_by_name(self) -> dict[str, dict[str, Any]]:
        """Aggregate metrics by name (min, max, mean, count)."""
        summary: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"values": []})
        for point in self._metrics:
            summary[point.name]["values"].append(point.value)

        result = {}
        for name, data in summary.items():
            values = data["values"]
            result[name] = {
                "count": len(values),
                "min": min(values),
                "max": max(values),
                "mean": sum(values) / len(values),
                "latest": values[-1] if values else 0,
            }
        return result


class ServiceRegistry:
    """Dependency injection container — register and retrieve services."""

    def __init__(self):
        self._services: dict[type, Any] = {}
        self._factories: dict[type, Callable[[], Any]] = {}
        self._singletons: dict[type, Any] = {}

    def register(self, service_type: type, instance: Any) -> None:
        """Register a singleton service instance."""
        self._services[service_type] = instance

    def register_factory(self, service_type: type, factory: Callable[[], Any]) -> None:
        """Register a factory function for lazy instantiation."""
        self._factories[service_type] = factory

    def get(self, service_type: type) -> Any:
        """Retrieve a service (from instance, factory, or error)."""
        if service_type in self._services:
            return self._services[service_type]

        if service_type in self._factories:
            if service_type not in self._singletons:
                self._singletons[service_type] = self._factories[service_type]()
            return self._singletons[service_type]

        raise ValueError(f"Service {service_type} not registered")

    def has(self, service_type: type) -> bool:
        """Check if service is registered."""
        return service_type in self._services or service_type in self._factories

    def get_all(self) -> dict[type, Any]:
        """Get all registered services."""
        result = self._services.copy()
        for svc_type, factory in self._factories.items():
            if svc_type not in result:
                result[svc_type] = self.get(svc_type)
        return result


__all__ = [
    "EventType",
    "LabEvent",
    "EventBus",
    "CacheLayer",
    "MetricsCollector",
    "ServiceRegistry",
]
