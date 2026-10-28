"""FastAPI routes for Market Cap terminal and local market data service."""

from __future__ import annotations

from typing import Any

from traderbot.marketcap.service import get_marketcap_service


def register_marketcap_routes(app) -> None:
    from fastapi import HTTPException, Query
    from fastapi.responses import JSONResponse

    @app.get("/api/marketcap/global")
    def api_marketcap_global(refresh: bool = Query(False)) -> dict[str, Any]:
        service = get_marketcap_service()
        return service.get_global_metrics(force_refresh=refresh)

    @app.get("/api/marketcap/coins")
    def api_marketcap_coins(
        page: int = Query(1, ge=1),
        limit: int = Query(50, ge=1, le=250),
        category: str = Query("all"),
        search: str = Query(""),
        sort_by: str = Query("market_cap"),
        sort_dir: str = Query("desc"),
        refresh: bool = Query(False),
    ) -> dict[str, Any]:
        service = get_marketcap_service()
        return service.get_coins(
            page=page,
            limit=limit,
            category=category,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            force_refresh=refresh,
        )

    @app.get("/api/marketcap/coin/{coin_id}")
    def api_marketcap_coin_detail(coin_id: str) -> dict[str, Any]:
        service = get_marketcap_service()
        coin = service.get_coin_details(coin_id)
        if coin is None:
            raise HTTPException(status_code=404, detail=f"Coin '{coin_id}' not found")
        return coin

    @app.post("/api/marketcap/refresh")
    def api_marketcap_refresh() -> dict[str, Any]:
        service = get_marketcap_service()
        return service.refresh_cache()
