"""
Scalable Lab API routes — leverages core.py architecture.

This extends the main app.py with new endpoints for:
- Service discovery
- Cache management & health
- Metrics dashboard
- Async job status streaming
"""

from __future__ import annotations

import logging
from typing import Any

from lab.core import EventBus, CacheLayer, MetricsCollector, ServiceRegistry

logger = logging.getLogger(__name__)


def attach_infrastructure_routes(app: Any, registry: ServiceRegistry) -> None:
    """Attach scalable infrastructure endpoints to FastAPI app."""

    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse
    import json
    import asyncio

    @app.get("/api/infrastructure/services")
    def list_services():
        """Service registry introspection — what services are available."""
        registry_data = registry.get_all()
        return {
            "services": {
                service_type.__name__: {
                    "type": service_type.__name__,
                    "module": service_type.__module__,
                }
                for service_type in registry_data.keys()
            }
        }

    @app.get("/api/infrastructure/cache/stats")
    def cache_stats():
        """Cache performance metrics — useful for optimization."""
        try:
            cache: CacheLayer = registry.get(CacheLayer)
            return cache.stats()
        except ValueError:
            raise HTTPException(status_code=503, detail="Cache service not available")

    @app.post("/api/infrastructure/cache/invalidate")
    def cache_invalidate(key: str):
        """Manually invalidate a cache key."""
        try:
            cache: CacheLayer = registry.get(CacheLayer)
            cache.invalidate(key)
            return {"status": "invalidated", "key": key}
        except ValueError:
            raise HTTPException(status_code=503, detail="Cache service not available")

    @app.get("/api/infrastructure/metrics/recent")
    def get_recent_metrics(since_seconds: int | None = None):
        """Get recent metrics for UI dashboard."""
        try:
            metrics: MetricsCollector = registry.get(MetricsCollector)
            since = metrics._metrics[-1].timestamp - since_seconds if since_seconds and metrics._metrics else None
            points = metrics.get_metrics(since)
            return {
                "metrics": [p.to_dict() for p in points],
                "count": len(points),
                "summary": metrics.summary_by_name(),
            }
        except ValueError:
            raise HTTPException(status_code=503, detail="Metrics service not available")

    @app.get("/api/infrastructure/metrics/gauges")
    def get_gauges():
        """Current gauge readings (memory, connections, etc)."""
        try:
            metrics: MetricsCollector = registry.get(MetricsCollector)
            return metrics.get_gauges()
        except ValueError:
            raise HTTPException(status_code=503, detail="Metrics service not available")

    @app.get("/api/infrastructure/events/recent")
    def get_recent_events(event_type: str | None = None):
        """Get recent Lab events (debugging, audit trail)."""
        try:
            event_bus: EventBus = registry.get(EventBus)
            from lab.core import EventType

            event_enum = EventType[event_type] if event_type else None
            events = event_bus.get_event_log(event_enum)
            return {
                "events": [e.to_dict() for e in events[-100:]],  # Last 100
                "count": len(events),
            }
        except ValueError:
            raise HTTPException(status_code=503, detail="Event bus not available")
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Unknown event type: {event_type}")

    @app.websocket("/ws/events")
    async def websocket_events(websocket: Any):
        """WebSocket: stream Lab events to UI in real-time."""
        try:
            event_bus: EventBus = registry.get(EventBus)
        except ValueError:
            await websocket.close(code=1008, reason="Event bus not available")
            return

        await websocket.accept()

        async def event_generator():
            """Emit events to client."""
            last_index = 0
            while True:
                try:
                    events = event_bus.get_event_log()
                    for event in events[last_index:]:
                        yield json.dumps(event.to_dict()) + "\n"
                    last_index = len(events)
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.exception(f"WebSocket event stream error: {e}")
                    break

        try:
            async for message in event_generator():
                await websocket.send_text(message)
        except Exception as e:
            logger.debug(f"WebSocket closed: {e}")
        finally:
            await websocket.close()

    @app.get("/api/infrastructure/health")
    def infra_health():
        """Detailed health check — all services, cache, metrics."""
        try:
            cache: CacheLayer = registry.get(CacheLayer)
            cache_stats = cache.stats()
        except:
            cache_stats = {"error": "unavailable"}

        try:
            metrics: MetricsCollector = registry.get(MetricsCollector)
            metrics_count = len(metrics._metrics)
        except:
            metrics_count = 0

        try:
            event_bus: EventBus = registry.get(EventBus)
            event_count = len(event_bus._event_log)
        except:
            event_count = 0

        return {
            "status": "ok",
            "cache": cache_stats,
            "metrics": {"count": metrics_count},
            "events": {"count": event_count},
            "services": list(registry.get_all().keys()),
        }


__all__ = ["attach_infrastructure_routes"]
