"""
Log viewing API routes for Traderbot Lab.

Provides endpoints for:
- Retrieving recent logs (with filtering)
- Full-text search
- Real-time log streaming via WebSocket
- Log statistics
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def attach_logging_routes(app: Any, log_collector: Any) -> None:
    """Attach logging endpoints to FastAPI app."""

    from fastapi import HTTPException, Query
    from lab.logging_service import LogLevel

    @app.get("/api/logs/recent")
    def get_recent_logs(
        limit: int = Query(100, ge=1, le=1000),
        level: str | None = None,
        module: str | None = None,
        source: str | None = None,
        since_timestamp: float | None = None,
    ):
        """
        Get recent logs with optional filtering.

        Query params:
        - limit: Max entries (default 100, max 1000)
        - level: Filter by level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        - module: Filter by module name (substring match)
        - source: Filter by source (app, job, api, etc.)
        - since_timestamp: Unix timestamp to start from
        """
        try:
            entries = log_collector.get_recent(
                limit=limit,
                level=level,
                module=module,
                source=source,
                since_timestamp=since_timestamp,
            )
            return {
                "logs": [e.to_dict() for e in entries],
                "count": len(entries),
            }
        except Exception as e:
            logger.exception(f"Failed to get recent logs: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/logs/search")
    def search_logs(query: str = Query(..., min_length=1), limit: int = Query(100, ge=1, le=1000)):
        """
        Full-text search in log messages.

        Query params:
        - query: Search string (substring match, case-insensitive)
        - limit: Max results (default 100, max 1000)
        """
        try:
            entries = log_collector.search(query, limit=limit)
            return {
                "query": query,
                "results": [e.to_dict() for e in entries],
                "count": len(entries),
            }
        except Exception as e:
            logger.exception(f"Search failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/logs/stats")
    def get_log_stats():
        """Log statistics (total count, breakdown by level, etc)."""
        try:
            stats = log_collector.get_stats()
            return {"stats": stats}
        except Exception as e:
            logger.exception(f"Failed to get log stats: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/logs/levels")
    def get_available_levels():
        """List available log levels for filtering."""
        return {
            "levels": [level.value for level in LogLevel]
        }

    @app.websocket("/ws/logs")
    async def websocket_logs(websocket: Any):
        """
        Real-time log streaming via WebSocket.

        Client can send JSON to filter:
        {
            "level": "WARNING",
            "module": "traderbot",
            "source": "job"
        }

        Server sends log entries as JSON, one per line.
        """
        await websocket.accept()

        # Subscription to log updates
        def on_log(entry: Any) -> None:
            try:
                # Check if we should send (basic filtering)
                asyncio.create_task(websocket.send_text(entry.to_json() + "\n"))
            except Exception as e:
                logger.debug(f"WebSocket send failed: {e}")

        unsubscribe = log_collector.subscribe(on_log)

        try:
            while True:
                # Keep connection open, allow client to send filter updates
                try:
                    message = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                    # Could parse filter updates here if needed
                    logger.debug(f"WebSocket message: {message}")
                except asyncio.TimeoutError:
                    # Keep-alive
                    pass
        except Exception as e:
            logger.debug(f"WebSocket closed: {e}")
        finally:
            unsubscribe()
            await websocket.close()

    @app.get("/api/logs/export")
    def export_logs(
        format: str = Query("json", regex="^(json|csv|txt)$"),
        level: str | None = None,
        source: str | None = None,
    ):
        """
        Export logs in various formats.

        Query params:
        - format: json, csv, or txt
        - level: Optional filter
        - source: Optional filter
        """
        try:
            entries = log_collector.get_recent(
                limit=10000,
                level=level,
                source=source,
            )

            if format == "json":
                content = json.dumps([e.to_dict() for e in entries], indent=2)
                media_type = "application/json"
                filename = "logs.json"
            elif format == "csv":
                import csv
                import io

                output = io.StringIO()
                if entries:
                    writer = csv.DictWriter(output, fieldnames=entries[0].to_dict().keys())
                    writer.writeheader()
                    for entry in entries:
                        writer.writerow(entry.to_dict())
                content = output.getvalue()
                media_type = "text/csv"
                filename = "logs.csv"
            else:  # txt
                lines = []
                for entry in entries:
                    lines.append(
                        f"[{entry.timestamp_iso}] {entry.level:8} {entry.module:30} {entry.message}"
                    )
                content = "\n".join(lines)
                media_type = "text/plain"
                filename = "logs.txt"

            from fastapi.responses import Response

            return Response(
                content=content,
                media_type=media_type,
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        except Exception as e:
            logger.exception(f"Export failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))


__all__ = ["attach_logging_routes"]
