#!/usr/bin/env python3
"""Write synthetic pair/grid backtest summaries under results/external-strategies/."""

from __future__ import annotations

import json
from pathlib import Path

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.algorithms.strategies.grid_trading import GridTradingAlgorithm
from traderbot.backtesting import run_backtest
from traderbot.backtesting.report import backtest_summary_dict
from traderbot.utils.pair_bars import align_bars_by_timestamp


def _bars(symbol: str, closes: list[float]) -> list[dict]:
    return [
        {
            "symbol": symbol,
            "resolution": "60",
            "timestamp": index * 3600,
            "datetime_utc": "",
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1.0,
        }
        for index, close in enumerate(closes)
    ]


def main() -> None:
    out_root = Path("results/external-strategies")
    out_root.mkdir(parents=True, exist_ok=True)
    hedge_closes = [100.0 + index * 0.05 for index in range(200)]
    primary_closes = [value * (1.02 + 0.01 * (index % 11 - 5) / 10) for index, value in enumerate(hedge_closes)]
    primary = _bars("ETHIRT", primary_closes)
    hedge = _bars("BTCIRT", hedge_closes)
    aligned = align_bars_by_timestamp(primary, hedge)
    pair_algo = algorithm_for_id("pair_trading", lookback=20, hedge_lookback=20, entry_z=1.2, exit_z=0.2)
    pair_result = run_backtest(pair_algo, aligned, initial_cash=10_000.0, fee_rate=0.002)
    pair_summary = backtest_summary_dict(pair_algo, pair_result, bars=len(aligned), extra={"strategy_id": "pair_trading"})
    (out_root / "pair_trading_synthetic.json").write_text(json.dumps(pair_summary, indent=2), encoding="utf-8")

    grid_closes = [40.0 + (index % 9 - 4) * 0.3 for index in range(120)]
    grid_algo = GridTradingAlgorithm()
    grid_result = run_backtest(grid_algo, _bars("BTCIRT", grid_closes), initial_cash=10_000.0, fee_rate=0.002)
    grid_summary = backtest_summary_dict(grid_algo, grid_result, bars=len(grid_closes), extra={"strategy_id": "grid_trading"})
    (out_root / "grid_trading_synthetic.json").write_text(json.dumps(grid_summary, indent=2), encoding="utf-8")
    print(json.dumps({"pair_trading": pair_summary["return_pct"], "grid_trading": grid_summary["return_pct"]}, indent=2))


if __name__ == "__main__":
    main()
