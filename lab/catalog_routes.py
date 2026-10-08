from __future__ import annotations

from dataclasses import asdict

from traderbot.algorithms.registry import list_strategies
from traderbot.terminal.catalog import catalog_dict


def register_catalog_routes(app) -> None:
    from fastapi import HTTPException, Query

    @app.get("/api/catalog/strategies")
    def api_catalog_strategies(implemented_only: bool = False):
        return [asdict(entry) for entry in list_strategies(implemented_only=implemented_only)]

    @app.get("/api/catalog/terminal")
    def api_catalog_terminal(implemented_only: bool = False):
        return catalog_dict(implemented_only=implemented_only)

    @app.get("/api/catalog/optimized-strategy-params")
    def api_catalog_optimized_strategy_params(
        strategy_id: str = Query(...),
        symbol: str | None = None,
        resolution: str | None = None,
        dataset_id: str | None = None,
    ):
        from lab.store import open_database
        from traderbot.algorithms.optimized_params import optimized_strategy_values

        csv_path = None
        market_symbol = symbol.strip().upper() if symbol else None
        bar_resolution = resolution
        if dataset_id:
            from lab.store.catalog import fetch_dataset

            connection = open_database()
            try:
                row = fetch_dataset(connection, dataset_id)
            finally:
                connection.close()
            if row is None:
                raise HTTPException(status_code=404, detail=f"dataset not found: {dataset_id}")
            csv_path = row.get("repo_path")
            if not market_symbol and row.get("symbol"):
                market_symbol = str(row["symbol"]).upper()
            if not bar_resolution and row.get("resolution"):
                bar_resolution = str(row["resolution"])
        try:
            values, sources = optimized_strategy_values(
                strategy_id,
                symbol=market_symbol,
                resolution=bar_resolution,
                csv_path=csv_path,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "strategy_id": strategy_id,
            "symbol": market_symbol,
            "resolution": bar_resolution,
            "values": values,
            "sources": sources,
        }

    @app.get("/api/catalog/strategy-params")
    def api_catalog_strategy_params(strategy_id: str = Query(...)):
        from traderbot.algorithms.cli_args import default_strategy_namespace
        from traderbot.algorithms.registry import strategy_param_names

        try:
            names = strategy_param_names(strategy_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        defaults = vars(default_strategy_namespace())
        fields: list[dict[str, object]] = []
        for name in names:
            default = defaults.get(name)
            if isinstance(default, bool):
                kind = "bool"
            elif isinstance(default, int):
                kind = "int"
            elif isinstance(default, float):
                kind = "float"
            elif default is None:
                kind = "optional_float"
            else:
                kind = "string"
            fields.append({"name": name, "kind": kind, "default": default})
        return {"strategy_id": strategy_id, "params": fields}

    @app.get("/api/markets/ohlc")
    def api_markets_ohlc(
        src: str = Query(..., min_length=1),
        dst: str = Query(..., min_length=1),
        resolution: str = Query("60"),
        max_bars: int = Query(300, ge=1, le=500),
    ):
        from traderbot.markets.market_data import fetch_recent_closed_bars, market_symbol

        symbol = market_symbol(src, dst)
        try:
            bars = fetch_recent_closed_bars(symbol=symbol, resolution=resolution, max_bars=max_bars)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "symbol": symbol,
            "src": src.strip().lower(),
            "dst": dst.strip().lower(),
            "resolution": resolution,
            "bars": bars,
        }
