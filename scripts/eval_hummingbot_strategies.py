#!/usr/bin/env python3
"""
Evaluate Hummingbot-inspired strategies per exchange (no live orders).

Writes ``results/hummingbot_eval/summary.json`` with Nobitex-style synthetic metrics
and Hyperliquid public API backtests when the network is available.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from traderbot.algorithms.strategies.funding_carry import FundingCarryAlgorithm
from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.algorithms.strategies.perp_market_making import PerpMarketMakingAlgorithm
from traderbot.algorithms.strategies.spot_grid import SpotGridAlgorithm
from traderbot.backtesting import run_backtest
from traderbot.backtesting.funding_carry_engine import run_funding_carry_backtest
from traderbot.backtesting.pair_engine import run_pair_backtest, run_pair_backtest_for_exchange
from traderbot.hyperliquid.funding import fetch_hyperliquid_funding_history
from traderbot.markets.execution_costs import execution_cost_profile
from traderbot.markets.exchange import fetch_live_recent_closed_bars


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
        }
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "reason": str(exc)}


def _hyperliquid_live_eval() -> dict:
    out: dict = {"status": "ok"}
    try:
        btc = fetch_live_recent_closed_bars(
            exchange="hyperliquid", src="btc", dst="usdt", resolution="60", max_bars=350,
        )
        eth = fetch_live_recent_closed_bars(
            exchange="hyperliquid", src="eth", dst="usdt", resolution="60", max_bars=350,
        )
        hl_taker = execution_cost_profile("hyperliquid", fee_role="taker")
        hl_maker = execution_cost_profile("hyperliquid", fee_role="maker")

        pair_algo = PairTradingAlgorithm(lookback_period=60, entry_threshold=2.0, exit_threshold=0.5)
        pair_result = run_pair_backtest_for_exchange(
            "hyperliquid",
            pair_algo,
            btc,
            eth,
            fee_rate=hl_taker.fee_rate,
            slippage_rate=hl_taker.slippage_rate,
        )

        closes = [float(bar["close"]) for bar in btc]
        grid_algo = SpotGridAlgorithm(
            start_price=min(closes) * 0.99,
            end_price=max(closes) * 1.01,
            grid_count=6,
            take_profit_pct=0.008,
        )
        grid_result = run_backtest(
            grid_algo,
            btc,
            fee_rate=hl_taker.fee_rate,
            slippage_rate=hl_taker.slippage_rate,
        )

        funding_events = fetch_hyperliquid_funding_history("btc", max_hours=400)
        funding_algo = FundingCarryAlgorithm()
        funding_result = run_funding_carry_backtest(
            funding_algo,
            btc,
            funding_events,
            fee_rate=hl_taker.fee_rate,
            slippage_rate=hl_taker.slippage_rate,
        )

        mm_algo = PerpMarketMakingAlgorithm(half_spread_pct=0.0004)
        mm_result = run_backtest(
            mm_algo,
            btc,
            fee_rate=hl_maker.fee_rate,
            slippage_rate=hl_maker.slippage_rate,
        )

        out["pair_trading_perp"] = {
            "bars": len(btc),
            "return_pct": pair_result.return_pct,
            "max_drawdown_pct": pair_result.max_drawdown_pct,
            "trade_count": len(pair_result.trades),
        }
        out["spot_grid_on_perp_candles"] = {
            "return_pct": grid_result.return_pct,
            "trade_count": len(grid_result.trades),
        }
        out["funding_carry"] = {
            "return_pct": funding_result.return_pct,
            "total_funding_pnl": funding_result.total_funding_pnl,
            "trade_count": funding_result.trade_count,
        }
        out["perp_market_making_maker_fee"] = {
            "return_pct": mm_result.return_pct,
            "trade_count": len(mm_result.trades),
        }
    except Exception as exc:  # noqa: BLE001
        out = {"status": "error", "reason": str(exc)}
    return out


def main() -> None:
    out_dir = Path("results/hummingbot_eval")
    out_dir.mkdir(parents=True, exist_ok=True)

    nobitex_costs = execution_cost_profile("nobitex", fee_role="taker")
    grid_prices = [100.0] * 4 + [97.0, 95.0, 94.0, 96.0, 99.0, 101.0, 103.0, 105.0]
    grid_algo = SpotGridAlgorithm(start_price=90.0, end_price=110.0, grid_count=6, take_profit_pct=0.02)
    grid_nobitex = run_backtest(
        grid_algo,
        _synthetic_bars(grid_prices, "BTCIRT"),
        fee_rate=nobitex_costs.fee_rate,
        slippage_rate=nobitex_costs.slippage_rate,
    )

    bar_count = 150
    dominant = [100.0 + index * 0.04 for index in range(bar_count)]
    hedge = [50.0 + index * 0.02 for index in range(bar_count)]
    pair_algo = PairTradingAlgorithm(lookback_period=40, entry_threshold=1.8, exit_threshold=0.5)
    pair_nobitex = run_pair_backtest(
        pair_algo,
        _synthetic_bars(dominant, "BTCIRT"),
        _synthetic_bars(hedge, "ETHIRT"),
        fee_rate=nobitex_costs.fee_rate,
        slippage_rate=nobitex_costs.slippage_rate,
    )

    summary = {
        "hummingbot_upstream_grid_tests": _try_hummingbot_grid_tests(),
        "nobitex": {
            "execution_costs_taker": nobitex_costs.fee_rate,
            "spot_grid_synthetic": {
                "return_pct": grid_nobitex.return_pct,
                "trade_count": len(grid_nobitex.trades),
            },
            "pair_trading_spot_synthetic": {
                "return_pct": pair_nobitex.return_pct,
                "max_drawdown_pct": pair_nobitex.max_drawdown_pct,
                "trade_count": len(pair_nobitex.trades),
            },
            "rejected": {
                "funding_carry": "No perp funding on Nobitex.",
                "perp_market_making": "Spot book; use Hyperliquid for maker perp sim.",
                "spot_perp_arbitrage": "No perps on Nobitex.",
            },
        },
        "hyperliquid": {
            "live_public_api": _hyperliquid_live_eval(),
            "notes": {
                "pair_trading": "Perp long/short legs via run_perp_pair_backtest.",
                "pure_market_making": "Adopted as simplified perp_market_making with maker fee tier.",
                "cross_exchange_mm": "Still rejected — single-venue scope.",
            },
        },
    }
    out_path = out_dir / "summary.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
