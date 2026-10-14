from __future__ import annotations

from pathlib import Path
from typing import Any

from starlette.responses import JSONResponse

from traderbot.algorithms.registry import pair_algorithm_for_id
from traderbot.backtesting.pair_engine import run_pair_backtest
from traderbot.utils.bars import load_bars_csv


def register_pair_routes(app, get_connection) -> None:
    @app.post("/api/strategies/pair-backtest")
    def api_pair_backtest(body: dict[str, Any]):
        dominant_csv = Path(str(body.get("dominant_csv") or ""))
        hedge_csv = Path(str(body.get("hedge_csv") or ""))
        if not dominant_csv.is_file() or not hedge_csv.is_file():
            return JSONResponse(
                status_code=400,
                content={"error": "dominant_csv and hedge_csv must be existing file paths"},
            )

        lookback = int(body.get("lookback_period") or 60)
        entry = float(body.get("entry_threshold") or 2.0)
        exit_threshold = float(body.get("exit_threshold") or 0.5)
        hedge_ratio = float(body.get("hedge_ratio") or 1.0)
        fee_rate = float(body.get("fee_rate") or 0.001)
        slippage_rate = float(body.get("slippage_rate") or 0.0005)
        initial_cash = float(body.get("initial_cash") or 10_000.0)

        algorithm = pair_algorithm_for_id(
            "pair_trading",
            lookback_period=lookback,
            entry_threshold=entry,
            exit_threshold=exit_threshold,
        )
        result = run_pair_backtest(
            algorithm,
            load_bars_csv(dominant_csv),
            load_bars_csv(hedge_csv),
            initial_cash=initial_cash,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            hedge_ratio=hedge_ratio,
        )
        return {
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
