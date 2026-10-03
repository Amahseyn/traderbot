import argparse
import json
import sys
from pathlib import Path

from traderbot.algorithms.registry import (
    algorithm_for_id,
    implemented_strategy_ids,
    strategy_kwargs_from_namespace,
)
from traderbot.algorithms.visualize import add_visualization_flags, wants_visualization
from traderbot.backtesting import load_bars_csv, run_backtest, save_backtest_result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Backtest an algorithm on OHLC CSV (from traderbot export)",
    )
    parser.add_argument("csv", type=Path, help="CSV path, e.g. data/BTCIRT_D.csv")
    parser.add_argument("--cash", type=float, default=10_000.0, help="Starting cash")
    parser.add_argument("--fee", type=float, default=0.0, help="Fee rate per trade (0–1)")
    parser.add_argument(
        "--strategy",
        choices=implemented_strategy_ids(),
        default="sma_cross",
        help="Rule-based strategy (see: traderbot strategy catalog)",
    )
    parser.add_argument("--fast", type=int, default=5, help="SMA/EMA/MACD fast window")
    parser.add_argument("--slow", type=int, default=20, help="SMA/EMA/MACD slow window")
    parser.add_argument("--signal", type=int, default=9, help="MACD signal period")
    parser.add_argument("--period", type=int, default=14, help="RSI or Bollinger lookback")
    parser.add_argument("--oversold", type=float, default=30.0)
    parser.add_argument("--overbought", type=float, default=70.0)
    parser.add_argument("--num-std", type=float, default=2.0)
    parser.add_argument("--out", type=Path, default=None, help="Optional output directory for JSON + charts")
    add_visualization_flags(parser)
    args = parser.parse_args(argv)

    bars = load_bars_csv(args.csv)
    if not bars:
        print("No bars in CSV", file=sys.stderr)
        sys.exit(1)

    algo = algorithm_for_id(args.strategy, **strategy_kwargs_from_namespace(args.strategy, args))
    result = run_backtest(algo, bars, initial_cash=args.cash, fee_rate=args.fee)
    summary = {
        "strategy_id": args.strategy,
        "algorithm": algo.name,
        "bars": len(bars),
        "trades": len(result.trades),
        "initial_cash": result.initial_cash,
        "final_equity": round(result.final_equity, 4),
        "return_pct": round(result.return_pct, 4),
    }
    print(json.dumps(summary, indent=2))
    if args.out is not None:
        save_backtest_result(
            algo,
            result,
            args.out,
            bars=len(bars),
            bar_rows=bars,
            visualize=wants_visualization(args, has_out=True),
            extra={"strategy_id": args.strategy},
        )


if __name__ == "__main__":
    main()
