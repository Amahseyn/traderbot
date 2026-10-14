#!/usr/bin/env python3
"""
Evaluate Hummingbot strategy concepts offline (no live trading).

Writes ``results/hummingbot_eval/summary.json`` with traderbot backtest metrics and notes
from upstream Hummingbot test runs when available.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.algorithms.strategies.spot_grid import SpotGridAlgorithm
from traderbot.backtesting import run_backtest
from traderbot.backtesting.pair_engine import run_pair_backtest


def _synthetic_bars(closes: list[float], symbol: str) -> list[dict]:
    return [
        {
            "symbol": symbol,
            "resolution": "60",
            "timestamp": index * 3600,
            "open": price,
            "high": price * 1.01,
            "low": price * 0.99,
            "close": price,
            "volume": 1.0,
        }
        for index, price in enumerate(closes)
    ]


def _try_hummingbot_grid_tests() -> dict:
    hb_root = Path("/tmp/hummingbot")
    test_path = hb_root / "test/hummingbot/strategy_v2/backtesting/executors_simulator/test_grid_executor_simulator.py"
    if not test_path.is_file():
        return {"status": "skipped", "reason": "hummingbot clone not found at /tmp/hummingbot"}
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", str(test_path), "-q"],
            cwd=hb_root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        return {
            "status": "ok" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "stdout_tail": completed.stdout[-2000:],
            "stderr_tail": completed.stderr[-2000:],
        }
    except Exception as exc:  # noqa: BLE001 — report script failures
        return {"status": "error", "reason": str(exc)}


def main() -> None:
    out_dir = Path("results/hummingbot_eval")
    out_dir.mkdir(parents=True, exist_ok=True)

    grid_prices = [100.0] * 4 + [97.0, 95.0, 94.0, 96.0, 99.0, 101.0, 103.0, 105.0]
    grid_algo = SpotGridAlgorithm(start_price=90.0, end_price=110.0, grid_count=6, take_profit_pct=0.02)
    grid_result = run_backtest(grid_algo, _synthetic_bars(grid_prices, "BTCIRT"), fee_rate=0.001)

    bar_count = 150
    dominant = [100.0 + index * 0.04 for index in range(bar_count)]
    hedge = [50.0 + index * 0.02 for index in range(bar_count)]
    pair_algo = PairTradingAlgorithm(lookback_period=40, entry_threshold=1.8, exit_threshold=0.5)
    pair_result = run_pair_backtest(
        pair_algo,
        _synthetic_bars(dominant, "BTCIRT"),
        _synthetic_bars(hedge, "ETHIRT"),
        fee_rate=0.001,
        slippage_rate=0.0005,
    )

    summary = {
        "hummingbot_upstream_grid_tests": _try_hummingbot_grid_tests(),
        "traderbot_adoptions": {
            "spot_grid": {
                "return_pct": grid_result.return_pct,
                "trade_count": len(grid_result.trades),
                "final_equity": grid_result.final_equity,
                "suitability_nobitex": "moderate — works in ranging spot books; set bounds from recent range; mind taker fees.",
            },
            "pair_trading": {
                "return_pct": pair_result.return_pct,
                "max_drawdown_pct": pair_result.max_drawdown_pct,
                "trade_count": len(pair_result.trades),
                "final_equity": pair_result.final_equity,
                "suitability_nobitex": "good — correlated IRT/USDT legs (e.g. BTC-IRT vs ETH-IRT); spot rebalance only.",
            },
        },
        "rejected": {
            "pure_market_making": "Needs sustained maker flow and tight spreads; Nobitex retail taker fees erode edge.",
            "cross_exchange_market_making": "Requires multi-venue inventory and transfer latency; out of scope for Nobitex-only.",
            "spot_perpetual_arbitrage": "No Nobitex perps in traderbot stack.",
            "amm_arb": "DEX/CEX bridge not applicable to Nobitex spot.",
            "avellaneda_market_making": "Inventory/risk model needs maker rebates and deep book — poor fit at retail fees.",
        },
    }
    out_path = out_dir / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
