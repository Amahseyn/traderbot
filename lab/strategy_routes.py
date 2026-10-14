from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.responses import JSONResponse

from traderbot.algorithms.registry import algorithm_for_id, pair_algorithm_for_id
from traderbot.algorithms.strategy_exchanges import STRATEGY_EXCHANGE_SUPPORT, exchanges_for_strategy
from traderbot.algorithms.strategies.funding_carry import FundingCarryAlgorithm
from traderbot.backtesting import run_backtest
from traderbot.backtesting.funding_carry_engine import run_funding_carry_backtest
from traderbot.backtesting.pair_engine import run_pair_backtest_for_exchange
from traderbot.hyperliquid.funding import fetch_hyperliquid_funding_history
from traderbot.markets.execution_costs import execution_cost_profile, list_supported_exchanges
from traderbot.markets.exchange import fetch_live_recent_closed_bars, normalize_live_exchange
from traderbot.utils.bars import load_bars_csv


def _load_pair_bars(
    body: dict[str, Any],
    *,
    leg: str,
) -> list[dict[str, Any]]:
    exchange = normalize_live_exchange(str(body.get("exchange") or "nobitex"))
    csv_key = f"{leg}_csv"
    csv_path = str(body.get(csv_key) or "").strip()
    if csv_path:
        path = Path(csv_path)
        if not path.is_file():
            raise ValueError(f"{csv_key} not found: {csv_path}")
        return load_bars_csv(path)

    src_key = f"{leg}_src"
    src = str(body.get(src_key) or "").strip()
    if not src:
        raise ValueError(f"provide {csv_key} or {src_key}")
    dst = str(body.get("dst") or "usdt").strip().lower()
    resolution = str(body.get("resolution") or "60")
    max_bars = int(body.get("max_bars") or 400)
    return fetch_live_recent_closed_bars(
        exchange=exchange,
        src=src,
        dst=dst,
        resolution=resolution,
        max_bars=max_bars,
    )


def register_strategy_routes(app, get_connection) -> None:
    @app.get("/api/strategies/exchange-catalog")
    def api_strategy_exchange_catalog():
        profiles = {
            exchange: {
                role: {
                    "fee_rate": execution_cost_profile(exchange, fee_role=role).fee_rate,
                    "slippage_rate": execution_cost_profile(exchange, fee_role=role).slippage_rate,
                }
                for role in ("taker", "maker")
            }
            for exchange in list_supported_exchanges()
        }
        return {
            "exchanges": list(list_supported_exchanges()),
            "strategies": {
                strategy_id: list(exchanges)
                for strategy_id, exchanges in STRATEGY_EXCHANGE_SUPPORT.items()
            },
            "execution_costs": profiles,
        }

    @app.post("/api/strategies/pair-backtest")
    def api_pair_backtest(body: dict[str, Any]):
        try:
            exchange = normalize_live_exchange(str(body.get("exchange") or "nobitex"))
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

        if "hyperliquid" not in exchanges_for_strategy("pair_trading") or exchange not in exchanges_for_strategy(
            "pair_trading",
        ):
            return JSONResponse(status_code=400, content={"error": f"pair_trading not supported on {exchange}"})

        fee_role = str(body.get("fee_role") or "taker").strip().lower()
        if fee_role not in ("taker", "maker"):
            return JSONResponse(status_code=400, content={"error": "fee_role must be taker or maker"})
        costs = execution_cost_profile(exchange, fee_role=fee_role)  # type: ignore[arg-type]

        try:
            dominant_bars = _load_pair_bars(body, leg="dominant")
            hedge_bars = _load_pair_bars(body, leg="hedge")
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

        lookback = int(body.get("lookback_period") or 60)
        entry = float(body.get("entry_threshold") or 2.0)
        exit_threshold = float(body.get("exit_threshold") or 0.5)
        hedge_ratio = float(body.get("hedge_ratio") or 1.0)
        initial_cash = float(body.get("initial_cash") or 10_000.0)
        fee_rate = float(body.get("fee_rate") if body.get("fee_rate") is not None else costs.fee_rate)
        slippage_rate = float(
            body.get("slippage_rate") if body.get("slippage_rate") is not None else costs.slippage_rate,
        )

        algorithm = pair_algorithm_for_id(
            "pair_trading",
            lookback_period=lookback,
            entry_threshold=entry,
            exit_threshold=exit_threshold,
        )
        result = run_pair_backtest_for_exchange(
            exchange,
            algorithm,
            dominant_bars,
            hedge_bars,
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            hedge_ratio=hedge_ratio,
        )
        return {
            "exchange": exchange,
            "fee_role": fee_role,
            "initial_cash": result.initial_cash,
            "final_equity": result.final_equity,
            "return_pct": result.return_pct,
            "max_drawdown_pct": result.max_drawdown_pct,
            "total_fees": result.total_fees,
            "trade_count": len(result.trades),
            "equity_curve": result.equity_curve[-500:],
            "spread_curve": result.spread_curve[-500:],
            "z_score_curve": result.z_score_curve[-500:],
            "trades": [
                {
                    "timestamp": trade.timestamp,
                    "leg": trade.leg,
                    "action": trade.action,
                    "price": trade.price,
                    "size": trade.size,
                    "fee": trade.fee,
                }
                for trade in result.trades[-100:]
            ],
        }

    @app.post("/api/strategies/funding-backtest")
    def api_funding_backtest(body: dict[str, Any]):
        try:
            exchange = normalize_live_exchange(str(body.get("exchange") or "hyperliquid"))
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})
        if exchange != "hyperliquid":
            return JSONResponse(
                status_code=400,
                content={"error": "funding_carry is only supported on hyperliquid"},
            )

        src = str(body.get("src") or "btc").strip()
        fee_role = str(body.get("fee_role") or "taker").strip().lower()
        costs = execution_cost_profile("hyperliquid", fee_role=fee_role if fee_role == "maker" else "taker")  # type: ignore[arg-type]
        resolution = str(body.get("resolution") or "60")
        max_bars = int(body.get("max_bars") or 400)
        max_hours = int(body.get("max_funding_hours") or max_bars)

        try:
            price_bars = fetch_live_recent_closed_bars(
                exchange="hyperliquid",
                src=src,
                dst="usdt",
                resolution=resolution,
                max_bars=max_bars,
            )
            funding_events = fetch_hyperliquid_funding_history(src, max_hours=max_hours)
        except Exception as exc:  # noqa: BLE001 — surface API errors to UI
            return JSONResponse(status_code=502, content={"error": str(exc)})

        algorithm = FundingCarryAlgorithm(
            entry_funding_rate=float(body.get("entry_funding_rate") or 0.00004),
            exit_funding_rate=float(body.get("exit_funding_rate") or 0.00001),
            position_fraction=float(body.get("position_fraction") or 0.5),
        )
        result = run_funding_carry_backtest(
            algorithm,
            price_bars,
            funding_events,
            fee_rate=float(body.get("fee_rate") if body.get("fee_rate") is not None else costs.fee_rate),
            slippage_rate=float(
                body.get("slippage_rate") if body.get("slippage_rate") is not None else costs.slippage_rate,
            ),
        )
        return {
            "exchange": "hyperliquid",
            "src": src.lower(),
            "return_pct": result.return_pct,
            "max_drawdown_pct": result.max_drawdown_pct,
            "total_funding_pnl": result.total_funding_pnl,
            "total_fees": result.total_fees,
            "trade_count": result.trade_count,
            "equity_curve": result.equity_curve[-500:],
            "funding_curve": result.funding_curve[-500:],
        }

    @app.post("/api/strategies/grid-backtest")
    def api_grid_backtest(body: dict[str, Any]):
        try:
            exchange = normalize_live_exchange(str(body.get("exchange") or "nobitex"))
        except ValueError as exc:
            return JSONResponse(status_code=400, content={"error": str(exc)})

        fee_role = str(body.get("fee_role") or "taker").strip().lower()
        costs = execution_cost_profile(exchange, fee_role=fee_role if fee_role == "maker" else "taker")  # type: ignore[arg-type]

        csv_path = str(body.get("csv") or "").strip()
        if csv_path:
            bars = load_bars_csv(Path(csv_path))
        else:
            src = str(body.get("src") or "btc").strip()
            dst = str(body.get("dst") or ("usdt" if exchange == "hyperliquid" else "rls"))
            bars = fetch_live_recent_closed_bars(
                exchange=exchange,
                src=src,
                dst=dst,
                resolution=str(body.get("resolution") or "60"),
                max_bars=int(body.get("max_bars") or 300),
            )

        if not bars:
            return JSONResponse(status_code=400, content={"error": "no bars loaded"})

        closes = [float(bar["close"]) for bar in bars]
        start_price = float(body.get("start_price") or min(closes) * 0.98)
        end_price = float(body.get("end_price") or max(closes) * 1.02)

        algo = algorithm_for_id(
            "spot_grid",
            start_price=start_price,
            end_price=end_price,
            grid_count=int(body.get("grid_count") or 5),
            take_profit_pct=float(body.get("take_profit_pct") or 0.01),
        )
        result = run_backtest(
            algo,
            bars,
            fee_rate=float(body.get("fee_rate") if body.get("fee_rate") is not None else costs.fee_rate),
            slippage_rate=float(
                body.get("slippage_rate") if body.get("slippage_rate") is not None else costs.slippage_rate,
            ),
        )
        return {
            "exchange": exchange,
            "return_pct": result.return_pct,
            "trade_count": len(result.trades),
            "final_equity": result.final_equity,
            "total_fees": result.total_fees,
        }
