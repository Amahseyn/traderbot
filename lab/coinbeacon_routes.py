from __future__ import annotations

from typing import Any

from traderbot.integrations.coinbeacon.client import (
    CoinBeaconClient,
    CoinBeaconError,
    coinbeacon_api_key_configured,
)


def register_coinbeacon_routes(app) -> None:
    from fastapi import HTTPException, Query, Request
    from fastapi.responses import JSONResponse

    def _client() -> CoinBeaconClient:
        try:
            return CoinBeaconClient()
        except CoinBeaconError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    def _json_with_credit_headers(payload: dict[str, Any], client: CoinBeaconClient) -> JSONResponse:
        headers: dict[str, str] = {}
        if client.last_credits:
            credits = client.last_credits
            if credits.cost is not None:
                headers["X-Credits-Cost"] = str(credits.cost)
            if credits.remaining is not None:
                headers["X-Credits-Remaining"] = str(credits.remaining)
            if credits.limit is not None:
                headers["X-Credits-Limit"] = str(credits.limit)
        return JSONResponse(content=payload, headers=headers)

    @app.get("/api/coinbeacon/status")
    def coinbeacon_status() -> dict[str, Any]:
        from traderbot.integrations.coinbeacon.keys import load_coinbeacon_api_keys

        key_count = len(load_coinbeacon_api_keys())
        if not coinbeacon_api_key_configured():
            return {"configured": False, "key_count": 0, "usage": None}
        client = _client()
        try:
            usage = client.usage()
        except CoinBeaconError as exc:
            return {"configured": True, "usage": None, "error": str(exc)}
        return {
            "configured": True,
            "key_count": key_count,
            "usage": usage,
            "credits": {
                "remaining": client.last_credits.remaining if client.last_credits else None,
                "limit": client.last_credits.limit if client.last_credits else None,
            },
        }

    @app.get("/api/coinbeacon/screener/presets")
    def coinbeacon_screener_presets() -> JSONResponse:
        client = _client()
        try:
            payload = client.get_public("public/screener/presets")
        except CoinBeaconError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _json_with_credit_headers(payload, client)

    @app.get("/api/coinbeacon/screener")
    def coinbeacon_screener(preset: str = Query(..., min_length=1)) -> JSONResponse:
        client = _client()
        try:
            payload = client.get_public("public/screener", params={"preset": preset})
        except CoinBeaconError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _json_with_credit_headers(payload, client)

    @app.get("/api/coinbeacon/trend-scanner")
    def coinbeacon_trend_scanner(
        exchange: str = Query("binance-futures"),
        sort: str = Query("1d"),
        dir: str = Query("desc"),
        quote: str | None = Query(None),
    ) -> JSONResponse:
        client = _client()
        params: dict[str, str] = {"exchange": exchange, "sort": sort, "dir": dir}
        if quote:
            params["quote"] = quote
        try:
            payload = client.get_public("public/trend-scanner", params=params)
        except CoinBeaconError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return _json_with_credit_headers(payload, client)

    @app.get("/api/coinbeacon/public/{path:path}")
    def coinbeacon_public_proxy(path: str, request: Request) -> JSONResponse:
        client = _client()
        params = {key: value for key, value in request.query_params.multi_items()}
        try:
            payload = client.get_public(f"public/{path}", params=params or None)
        except CoinBeaconError as exc:
            status = exc.status_code if exc.status_code and exc.status_code < 500 else 502
            raise HTTPException(status_code=status, detail=str(exc)) from exc
        return _json_with_credit_headers(payload, client)
