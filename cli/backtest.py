import argparse
import json
import sys
from pathlib import Path

from traderbot.algorithms.cli_args import add_strategy_param_flags
from traderbot.algorithms.registry import (
    algorithm_for_id,
    implemented_strategy_ids,
    strategy_kwargs_from_namespace,
)
from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest
from traderbot.algorithms.visualize import add_visualization_flags, wants_visualization
from traderbot.backtesting import load_bars_csv, run_backtest, save_backtest_result
from traderbot.data.intrahour import enrich_bars_for_csv
from traderbot.utils.trading_costs import (
    DEFAULT_BACKTEST_EXECUTION,
    resolve_cost_rates,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Backtest an algorithm on OHLC CSV (from traderbot export)",
    )
    parser.add_argument("csv", type=Path, help="CSV path, e.g. data/BTCIRT_D.csv")
    parser.add_argument("--cash", type=float, default=10_000.0, help="Starting cash")
    parser.add_argument(
        "--fee",
        type=float,
        default=None,
        help="Fee rate per trade (0–1); default: venue profile inferred from the CSV name",
    )
    parser.add_argument(
        "--strategy",
        choices=implemented_strategy_ids(),
        default="sma_cross",
        help="Rule-based strategy (see: traderbot strategy catalog)",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=None,
        help="Slippage rate per fill (fraction); default: venue profile",
    )
    parser.add_argument(
        "--execution",
        choices=["close", "next_open"],
        default=DEFAULT_BACKTEST_EXECUTION,
        help="Fill timing: signal-bar close or next-bar open",
    )
    add_strategy_param_flags(parser)
    parser.add_argument("--out", type=Path, default=None, help="Optional output directory for JSON + charts")
    add_visualization_flags(parser)
    args = parser.parse_args(argv)

    bars = enrich_bars_for_csv(load_bars_csv(args.csv), args.csv, args)
    if not bars:
        print("No bars in CSV", file=sys.stderr)
        sys.exit(1)

    namespace = namespace_for_strategy_backtest(args.strategy, args, csv_path=args.csv)
    algo = algorithm_for_id(args.strategy, **strategy_kwargs_from_namespace(args.strategy, namespace))
    fee_rate, slippage_rate = resolve_cost_rates(source=args.csv, fee=args.fee, slippage=args.slippage)
    result = run_backtest(
        algo,
        bars,
        initial_cash=args.cash,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        execution=args.execution,
    )
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
