from __future__ import annotations

from dataclasses import asdict

from traderbot.algorithms.registry import list_strategies
from traderbot.backtesting.engine import EXECUTION_MODES
from traderbot.backtesting.vectorbt import vectorbt_is_available
from traderbot.terminal.catalog import catalog_dict


def register_catalog_routes(app) -> None:
    from fastapi import HTTPException, Query

    @app.get("/api/catalog/backtest")
    def api_catalog_backtest():
        return {
            "vectorbt_available": vectorbt_is_available(),
            "execution_modes": list(EXECUTION_MODES),
        }

    @app.get("/api/catalog/strategies")
    def api_catalog_strategies(implemented_only: bool = False):
        return [asdict(entry) for entry in list_strategies(implemented_only=implemented_only)]

    @app.get("/api/catalog/finrl-trading")
    def api_catalog_finrl_trading():
        from traderbot.integrations.finrl_trading import capabilities_api_payload

        return capabilities_api_payload()

    @app.get("/api/catalog/wondertrader")
    def api_catalog_wondertrader():
        from traderbot.integrations.wondertrader import capabilities_api_payload

        return capabilities_api_payload()

    @app.get("/api/catalog/terminal")
    def api_catalog_terminal(implemented_only: bool = False):
        return catalog_dict(implemented_only=implemented_only)

    @app.get("/api/catalog/optimized-strategy-params")
    def api_catalog_optimized_strategy_params(
        strategy_id: str = Query(...),
        symbol: str | None = None,
        resolution: str | None = None,
        dataset_id: str | None = None,
        horizon_label: str | None = None,
    ):
        from lab.store import open_database
        from traderbot.algorithms.optimized_params import optimized_strategy_values

        csv_path = None
        market_symbol = symbol.strip().upper() if symbol else None
        bar_resolution = resolution
        dataset_horizon = None
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
            dataset_horizon = row.get("horizon_label")
            if not market_symbol and row.get("symbol"):
                market_symbol = str(row["symbol"]).upper()
            if not bar_resolution and row.get("resolution"):
                bar_resolution = str(row["resolution"])
        try:
            values, sources, sweep_meta = optimized_strategy_values(
                strategy_id,
                symbol=market_symbol,
                resolution=bar_resolution,
                csv_path=csv_path,
                horizon_label=horizon_label or dataset_horizon,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "strategy_id": strategy_id,
            "symbol": market_symbol,
            "resolution": bar_resolution,
            "values": values,
            "sources": sources,
            "sweep_meta": sweep_meta,
        }

    @app.get("/api/catalog/strategy-tune-grid")
    def api_catalog_strategy_tune_grid(strategy_id: str = Query(...), full: bool = False):
        from traderbot.algorithms.registry import backtest_strategy_ids
        from traderbot.backtesting.robust_defaults import tune_grid_for_strategy

        if strategy_id not in backtest_strategy_ids():
            raise HTTPException(status_code=404, detail=f"unsupported strategy_id={strategy_id!r}")
        try:
            param_grid = tune_grid_for_strategy(strategy_id, full=full)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"strategy_id": strategy_id, "full": full, "param_grid": param_grid}

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

    @app.get("/api/catalog/discovery-runs")
    def api_catalog_discovery_runs(limit: int = Query(50, ge=1, le=200)):
        from lab.store import open_database
        from lab.store.discovery import list_discovery_runs

        connection = open_database()
        try:
            return list_discovery_runs(connection, limit=limit)
        finally:
            connection.close()

    @app.get("/api/catalog/discovery-runs/by-job/{job_id}")
    def api_catalog_discovery_run_by_job(job_id: str):
        from fastapi import HTTPException

        from lab.store import open_database
        from lab.store.discovery import fetch_discovery_run_by_job_id

        connection = open_database()
        try:
            row = fetch_discovery_run_by_job_id(connection, job_id)
        finally:
            connection.close()
        if row is None:
            raise HTTPException(status_code=404, detail="discovery run not found for job")
        return row

    @app.get("/api/catalog/discovery-runs/{run_id}")
    def api_catalog_discovery_run(run_id: str):
        from fastapi import HTTPException

        from lab.store import open_database
        from lab.store.discovery import fetch_discovery_run

        connection = open_database()
        try:
            row = fetch_discovery_run(connection, run_id)
        finally:
            connection.close()
        if row is None:
            raise HTTPException(status_code=404, detail="discovery run not found")
        return row

    @app.get("/api/catalog/live-strategy-ranks")
    def api_catalog_live_strategy_ranks(
        src: str = Query(..., min_length=1),
        dst: str = Query(..., min_length=1),
        resolution: str = Query("60"),
        exchange: str = Query("hyperliquid"),
        max_bars: int = Query(100, ge=20, le=300),
        initial_cash: float | None = Query(default=None),
    ):
        from lab.live_strategy_ranks import rank_strategies_on_live_bars
        from lab.store import open_database
        from lab.store.queries import fetch_best_sweep

        try:
            payload = rank_strategies_on_live_bars(
                exchange=exchange,
                src=src,
                dst=dst,
                resolution=resolution,
                max_bars=max_bars,
                initial_cash=initial_cash,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        symbol = str(payload.get("symbol") or "").upper()
        connection = open_database()
        try:
            for row in payload.get("ranked", []):
                strategy_id = row.get("strategy_id")
                if not isinstance(strategy_id, str):
                    continue
                sweep = fetch_best_sweep(
                    connection,
                    strategy_id=strategy_id,
                    symbol=symbol or None,
                    resolution=resolution,
                )
                if sweep is None:
                    continue
                metrics = sweep.get("best_metrics") if isinstance(sweep.get("best_metrics"), dict) else {}
                if metrics.get("return_pct") is not None:
                    row["stored_sweep_return_pct"] = metrics.get("return_pct")
                if metrics.get("holdout_return_pct") is not None:
                    row["stored_sweep_holdout_return_pct"] = metrics.get("holdout_return_pct")
        finally:
            connection.close()
        return payload

    @app.get("/api/markets/ohlc")
    def api_markets_ohlc(
        src: str = Query(..., min_length=1),
        dst: str = Query(..., min_length=1),
        resolution: str = Query("60"),
        max_bars: int = Query(300, ge=1, le=500),
        exchange: str = Query("hyperliquid"),
    ):
        from traderbot.markets.exchange import fetch_live_recent_closed_bars, live_market_symbol, normalize_live_exchange

        live_exchange = normalize_live_exchange(exchange)
        symbol = live_market_symbol(live_exchange, src, dst)
        try:
            bars = fetch_live_recent_closed_bars(
                exchange=live_exchange,
                src=src,
                dst=dst,
                resolution=resolution,
                max_bars=max_bars,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "exchange": live_exchange,
            "symbol": symbol,
            "src": src.strip().lower(),
            "dst": dst.strip().lower(),
            "resolution": resolution,
            "bars": bars,
        }
