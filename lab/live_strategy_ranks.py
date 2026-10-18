from __future__ import annotations

from typing import Any

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.algorithms.registry import (
    algorithm_for_id,
    backtest_strategy_ids,
    list_strategies,
    strategy_kwargs_from_namespace,
)
from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest
from traderbot.algorithms.strategy_exchanges import strategy_supported_on
from traderbot.backtesting import backtest_summary_dict, run_backtest
from traderbot.backtesting.live_tune import fetch_live_tune_bars
from traderbot.markets.exchange import live_market_symbol, normalize_live_exchange
from traderbot.terminal.paper_portfolio import default_paper_initial_cash
from traderbot.utils.trading_costs import DEFAULT_BACKTEST_EXECUTION, DEFAULT_TRADE_FEE_RATE


def terminal_strategy_ids_for_exchange(exchange: str) -> list[str]:
    live_exchange = normalize_live_exchange(exchange)
    implemented = {entry.id for entry in list_strategies(implemented_only=True)}
    return [
        strategy_id
        for strategy_id in backtest_strategy_ids()
        if strategy_id in implemented and strategy_supported_on(strategy_id, live_exchange)
    ]


def rank_strategies_on_live_bars(
    *,
    exchange: str,
    src: str,
    dst: str,
    resolution: str,
    max_bars: int = 100,
    initial_cash: float | None = None,
    strategy_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Quick default-param backtests on recent closed exchange bars (for Live UI ordering)."""
    live_exchange = normalize_live_exchange(exchange)
    bar_src = src.strip().lower()
    bar_dst = dst.strip().lower()
    symbol = live_market_symbol(live_exchange, bar_src, bar_dst)
    if max_bars < 20:
        raise ValueError("max_bars must be at least 20 for strategy preview ranks")
    bars = fetch_live_tune_bars(
        exchange=live_exchange,
        src=bar_src,
        dst=bar_dst,
        interval=str(resolution),
        max_bars=max_bars,
    )
    cash = float(initial_cash) if initial_cash is not None else default_paper_initial_cash(bar_dst)
    if cash <= 0:
        raise ValueError("initial_cash must be positive")

    allowed = terminal_strategy_ids_for_exchange(live_exchange)
    if strategy_ids:
        allowed_set = set(strategy_ids)
        allowed = [sid for sid in allowed if sid in allowed_set]
    if not allowed:
        raise ValueError("no strategies available for this exchange")

    ranked: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for index, strategy_id in enumerate(allowed, start=1):
        namespace = namespace_for_strategy_backtest(
            strategy_id,
            default_strategy_namespace(),
        )
        kwargs = strategy_kwargs_from_namespace(strategy_id, namespace)
        try:
            algo = algorithm_for_id(strategy_id, **kwargs)
            result = run_backtest(
                algo,
                bars,
                initial_cash=cash,
                fee_rate=DEFAULT_TRADE_FEE_RATE,
                execution=DEFAULT_BACKTEST_EXECUTION,
            )
            row = backtest_summary_dict(algo, result, bars=len(bars), extra={"strategy_id": strategy_id})
        except Exception as exc:  # noqa: BLE001 — per-strategy preview; skip unsupported combos
            errors.append({"strategy_id": strategy_id, "error": str(exc)})
            continue
        ranked.append(
            {
                "strategy_id": strategy_id,
                "return_pct": row.get("return_pct"),
                "max_drawdown_pct": row.get("max_drawdown_pct"),
                "trade_count": row.get("trade_count"),
                "final_equity": row.get("final_equity"),
                "preview_index": index,
            },
        )

    ranked.sort(
        key=lambda row: (
            row.get("return_pct") is None,
            -(float(row["return_pct"]) if row.get("return_pct") is not None else 0.0),
        ),
    )
    for rank, row in enumerate(ranked, start=1):
        row["rank"] = rank

    return {
        "exchange": live_exchange,
        "symbol": symbol,
        "src": bar_src,
        "dst": bar_dst,
        "resolution": str(resolution),
        "bars": len(bars),
        "initial_cash": cash,
        "execution": DEFAULT_BACKTEST_EXECUTION,
        "ranked": ranked,
        "skipped": errors,
        "strategy_count": len(allowed),
    }
