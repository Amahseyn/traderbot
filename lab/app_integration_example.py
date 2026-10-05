"""
Example: Integrating new Lab architecture into existing app.py

This module shows exactly how to update the main Lab API factory
to use the new scalable infrastructure.
"""

# BEFORE (existing):
# def create_app(database_path: Path | None = None):
#     from fastapi import FastAPI, HTTPException, Query
#     from fastapi.middleware.cors import CORSMiddleware
#     # ... rest of existing code ...

# AFTER (with scalable architecture):

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def create_app_with_infrastructure(database_path: Path | None = None):
    """
    Enhanced create_app that integrates:
    - EventBus for decoupled events
    - CacheLayer for query caching (with optional Redis)
    - MetricsCollector for built-in observability
    - ServiceRegistry for DI
    """

    try:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError as import_error:
        raise ImportError(
            "Lab API requires optional dependencies. Install: pip install -e '.[ui]'",
        ) from import_error

    from lab.store import (
        default_database_path,
        fetch_dashboard_stats,
        open_database,
    )
    from lab.store.database import init_database
    from lab.core import (
        EventBus,
        CacheLayer,
        MetricsCollector,
        ServiceRegistry,
        LabEvent,
        EventType,
    )
    from lab.infrastructure_routes import attach_infrastructure_routes

    # Initialize service registry
    service_registry = ServiceRegistry()

    # Register infrastructure services
    event_bus = EventBus()
    cache_layer = CacheLayer(redis_url=os.getenv("REDIS_URL"))
    metrics_collector = MetricsCollector()

    service_registry.register(EventBus, event_bus)
    service_registry.register(CacheLayer, cache_layer)
    service_registry.register(MetricsCollector, metrics_collector)

    # Create FastAPI app
    app = FastAPI(title="Traderbot Lab API", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_connection():
        return open_database(database_path or default_database_path())

    @app.on_event("startup")
    def _lab_startup() -> None:
        from lab.jobs import reconcile_orphan_lab_jobs

        connection = get_connection()
        try:
            init_database(connection)
            connection.commit()
            reconcile_orphan_lab_jobs(connection)
            connection.commit()

            # Emit startup event
            event_bus.emit(
                LabEvent(
                    event_type=EventType.JOB_QUEUED,
                    source="lab.startup",
                    payload={"message": "Lab API initialized"},
                )
            )

            logger.info("Lab API started successfully")
        finally:
            connection.close()

    @app.get("/health")
    def health():
        """Health check — includes features and infrastructure status."""
        return {
            "status": "ok",
            "features": [
                "market_catalog",
                "datasets",
                "catalog_jobs",
                "pipelines",
                "experiment_sync",
                "live_job_logs",
                "auth_api",
                "terminal_jobs",
                "catalog_api",
                "infrastructure",  # NEW
            ],
            "infrastructure": {
                "cache_stats": cache_layer.stats(),
                "metrics_count": len(metrics_collector._metrics),
                "events_count": len(event_bus._event_log),
            },
        }

    @app.get("/api/stats")
    def api_stats():
        """Dashboard stats — cached for performance."""
        cache_key = "dashboard_stats"
        cached = cache_layer.get(cache_key)
        if cached is not None:
            metrics_collector.record("cache.hit", 1.0, tags={"key": cache_key})
            return cached

        connection = get_connection()
        try:
            with metrics_collector.timer("query.dashboard_stats"):
                stats = fetch_dashboard_stats(connection)
            cache_layer.set(cache_key, stats, ttl_seconds=30, source="api_stats")
            metrics_collector.record("cache.miss", 1.0, tags={"key": cache_key})
            return stats
        finally:
            connection.close()

    # Attach new infrastructure routes
    attach_infrastructure_routes(app, service_registry)

    # ... rest of existing routes (list_runs, etc.) unchanged ...
    # They can optionally use cache_layer.get/set() for performance

    return app, service_registry


# Usage in serve.py:
#
# def main(argv: list[str] | None = None) -> None:
#     import uvicorn
#     app, registry = create_app_with_infrastructure()
#     uvicorn.run(app, host="0.0.0.0", port=8765, reload=False)
#
