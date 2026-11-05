from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from traderbot.algorithms.strategies.bollinger import BollingerMeanReversionAlgorithm
from traderbot.algorithms.strategies.macd import MacdCrossAlgorithm
from traderbot.algorithms.strategies.rsi_trend import RsiTrendAlgorithm
from traderbot.algorithms.strategies.scalp_dip import ScalpDipAlgorithm
from traderbot.backtesting import run_backtest
from traderbot.backtesting.eval_data import fetch_history_bars

assets = ["btc", "eth", "sol", "arb", "doge"]
timeframes = ["5", "15", "60", "240"]

results: dict[str, dict[str, dict]] = defaultdict(dict)

print("Running Comprehensive Multi-Asset x Multi-Timeframe Verification...")

for asset in assets:
    for tf in timeframes:
        bars = fetch_history_bars(exchange="hyperliquid", symbol_key=asset, resolution=tf, months=6, use_cache=True)
        if not bars or len(bars) < 60:
            continue
        key = f"{asset.upper()}:{tf}"

        # 1. Bollinger Mean Reversion
        b_old = BollingerMeanReversionAlgorithm(period=20, num_std=2.0, exit_target="upper")
        res_b_old = run_backtest(b_old, bars, fee_rate=0.00045, slippage_rate=0.0002)
        b_new = BollingerMeanReversionAlgorithm(period=20, num_std=2.0, exit_target="mean")
        res_b_new = run_backtest(b_new, bars, fee_rate=0.00045, slippage_rate=0.0002)

        # 2. Scalp Dip
        s_old = ScalpDipAlgorithm(dip_lookback_bars=6, dip_pct=0.01, take_profit_pct=0.015, stop_loss_pct=0.01, trend_ema_period=0)
        res_s_old = run_backtest(s_old, bars, fee_rate=0.00045, slippage_rate=0.0002)
        s_new = ScalpDipAlgorithm(dip_lookback_bars=6, dip_pct=0.01, take_profit_pct=0.015, stop_loss_pct=0.01, trend_ema_period=50)
        res_s_new = run_backtest(s_new, bars, fee_rate=0.00045, slippage_rate=0.0002)

        # 3. RSI Trend
        r_old = RsiTrendAlgorithm(period=14, rsi_trend_entry=55, rsi_trend_exit=45, trend_filter_period=50, trailing_stop_pct=None)
        res_r_old = run_backtest(r_old, bars, fee_rate=0.00045, slippage_rate=0.0002)
        r_new = RsiTrendAlgorithm(period=14, rsi_trend_entry=55, rsi_trend_exit=45, trend_filter_period=50, trailing_stop_pct=0.035, stop_loss_pct=0.025)
        res_r_new = run_backtest(r_new, bars, fee_rate=0.00045, slippage_rate=0.0002)

        results[key]["bollinger"] = {
            "old_ret": round(res_b_old.return_pct, 2),
            "new_ret": round(res_b_new.return_pct, 2),
            "delta": round(res_b_new.return_pct - res_b_old.return_pct, 2),
            "old_trades": len(res_b_old.trades),
            "new_trades": len(res_b_new.trades),
        }
        results[key]["scalp_dip"] = {
            "old_ret": round(res_s_old.return_pct, 2),
            "new_ret": round(res_s_new.return_pct, 2),
            "delta": round(res_s_new.return_pct - res_s_old.return_pct, 2),
            "old_trades": len(res_s_old.trades),
            "new_trades": len(res_s_new.trades),
        }
        results[key]["rsi_trend"] = {
            "old_ret": round(res_r_old.return_pct, 2),
            "new_ret": round(res_r_new.return_pct, 2),
            "delta": round(res_r_new.return_pct - res_r_old.return_pct, 2),
            "old_trades": len(res_r_old.trades),
            "new_trades": len(res_r_new.trades),
        }

out_path = Path("results/remediation_benchmark.json")
out_path.parent.mkdir(parents=True, exist_ok=True)
out_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

header = f"{'Cell':<10} | {'Strategy':<12} | {'Old Return%':<12} | {'New Return%':<12} | {'Delta%':<10} | {'Status'}"
print("\n" + "=" * len(header))
print(header)
print("=" * len(header))

for cell, strats in sorted(results.items()):
    for s_name, data in strats.items():
        if data["new_ret"] > 0:
            status = "PROFIT"
        elif data["delta"] > 0:
            status = "IMPROVED"
        else:
            status = "NEUTRAL"
        old_r = f"{data['old_ret']:+.2f}%"
        new_r = f"{data['new_ret']:+.2f}%"
        delta_str = f"{data['delta']:+.2f}%"
        print(f"{cell:<10} | {s_name:<12} | {old_r:<12} | {new_r:<12} | {delta_str:<10} | {status}")

