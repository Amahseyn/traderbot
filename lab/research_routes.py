from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class PairBacktestBody(BaseModel):
    primary_csv: str = Field(..., min_length=1)
    hedge_csv: str = Field(..., min_length=1)
    cash: float = 10_000.0
    fee: float = 0.0
    slippage: float = 0.0
    lookback: int = 60
    hedge_lookback: int = 60
    entry_z: float = 2.0
    exit_z: float = 0.5
    use_dynamic_hedge_ratio: bool = True
    fixed_hedge_ratio: float = 1.0


def register_research_routes(app) -> None:
    from fastapi import HTTPException

    @app.post("/api/research/pair-backtest")
    def api_research_pair_backtest(payload: PairBacktestBody) -> dict[str, Any]:
        from traderbot.algorithms.cli_args import default_strategy_namespace
        from traderbot.backtesting.pair_research import run_pair_backtest_preview

        primary = Path(payload.primary_csv)
        hedge = Path(payload.hedge_csv)
        if not primary.is_file():
            raise HTTPException(status_code=404, detail=f"primary_csv not found: {primary}")
        if not hedge.is_file():
            raise HTTPException(status_code=404, detail=f"hedge_csv not found: {hedge}")
        namespace = default_strategy_namespace(
            lookback=payload.lookback,
            hedge_lookback=payload.hedge_lookback,
            entry_z=payload.entry_z,
            exit_z=payload.exit_z,
            use_dynamic_hedge_ratio=payload.use_dynamic_hedge_ratio,
            fixed_hedge_ratio=payload.fixed_hedge_ratio,
            hedge_csv=str(hedge),
        )
        try:
            return run_pair_backtest_preview(
                primary_csv=primary,
                hedge_csv=hedge,
                strategy_namespace=namespace,
                initial_cash=payload.cash,
                fee_rate=payload.fee,
                slippage_rate=payload.slippage,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
