from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from traderbot.backtesting.trade_stats import DEFAULT_MIN_TRADES

from traderbot.algorithms.registry import (
    algorithm_for_id,
    backtest_strategy_ids,
    implemented_strategy_ids,
    list_strategies,
    strategy_kwargs_from_namespace,
)
from traderbot.backtesting import backtest_summary_dict, save_backtest_result
from traderbot.algorithms.visualize import (
    add_visualization_flags,
    compare_visualization_paths_to_dict,
    render_compare_plots,
    wants_visualization,
)
from traderbot.backtesting import load_bars_csv, run_backtest, vectorbt_extra_for_backtest
from traderbot.data.intrahour import add_fine_coarse_flags, enrich_bars_for_csv
from traderbot.results.layout import (
    default_strategy_batch_out,
    default_strategy_compare_out,
    result_tree_at,
)
from traderbot.algorithms.cli_args import add_strategy_param_flags
from traderbot.utils.trading_costs import (
    DEFAULT_BACKTEST_EXECUTION,
    DEFAULT_TRADE_FEE_RATE,
)

def _add_vectorbt_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--vectorbt",
        action="store_true",
        help="Add vectorbt risk metrics (pip install 'traderbot[backtest]')",
    )


def _vectorbt_extra(
    algo,
    bars: list[dict],
    args: argparse.Namespace,
) -> dict[str, Any]:
    if not getattr(args, "vectorbt", False):
        return {}
    fee, slippage = _resolve_fee_slippage(args)
    extra = vectorbt_extra_for_backtest(
        algo,
        bars,
        initial_cash=args.cash,
        fee_rate=fee,
        slippage_rate=slippage,
        execution=getattr(args, "execution", DEFAULT_BACKTEST_EXECUTION),
    )
    if extra is None:
        print(
            "vectorbt not installed; skip --vectorbt or install traderbot[backtest]",
            file=sys.stderr,
        )
        return {}
    return extra


def _load_strategy_bars(csv_path: Path, args: argparse.Namespace) -> list[dict]:
    bars = load_bars_csv(csv_path)
    return enrich_bars_for_csv(bars, csv_path, args)


def _add_param_flags(parser: argparse.ArgumentParser) -> None:
    add_strategy_param_flags(parser)
    add_fine_coarse_flags(parser)


def _add_fill_flags(parser: argparse.ArgumentParser) -> None:
    from traderbot.utils.trading_costs import (
        DEFAULT_BACKTEST_EXECUTION,
        DEFAULT_SLIPPAGE_RATE,
        DEFAULT_TRADE_FEE_RATE,
    )

    parser.add_argument(
        "--exchange",
        choices=["hyperliquid", "nobitex"],
        default=None,
        help="Venue fee/slippage defaults (Hyperliquid perp: 0.045%% taker + 0.05%% slippage; "
        "Nobitex: 0.35%% taker + 0.1%%). Default: inferred from CSV name (*IRT → nobitex)",
    )
    parser.add_argument(
        "--fee-role",
        choices=["taker", "maker"],
        default="taker",
        help="With --exchange: maker or taker fee tier",
    )
    parser.add_argument(
        "--fee",
        type=float,
        default=None,
        help=f"Fee per fill (default: {DEFAULT_TRADE_FEE_RATE} or --exchange profile)",
    )
    parser.add_argument(
        "--slippage",
        type=float,
        default=None,
        help=f"Slippage per fill (default: {DEFAULT_SLIPPAGE_RATE} or --exchange profile)",
    )
    parser.add_argument(
        "--execution",
        choices=["close", "next_open"],
        default=DEFAULT_BACKTEST_EXECUTION,
        help="Fill timing: signal-bar close or next-bar open",
    )


def _algorithm_kwargs(
    strategy_id: str,
    args: argparse.Namespace,
    *,
    csv_path: Path | None = None,
) -> dict[str, Any]:
    from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest

    path = csv_path if csv_path is not None else getattr(args, "csv", None)
    namespace = namespace_for_strategy_backtest(strategy_id, args, csv_path=path)
    return strategy_kwargs_from_namespace(strategy_id, namespace)


def _print_run_trade_logs(algo, result, *, file=sys.stderr) -> None:
    from traderbot.backtesting.engine import build_cash_flow_summary

    print(f"\n[{algo.name}] trade logs ({len(result.trades)} fills):", file=file)
    for trade in result.trades:
        if trade.action == "buy":
            print(
                f"  BUY  bar={trade.timestamp} price={trade.price:.4f} size={trade.size:.6f} "
                f"cash_in={trade.cash_before:.2f} fee={trade.fee:.2f} "
                f"cash_after={trade.cash_after:.2f} position={trade.position_after:.6f}",
                file=file,
            )
        else:
            print(
                f"  SELL bar={trade.timestamp} price={trade.price:.4f} size={trade.size:.6f} "
                f"cash_out={trade.cash_after:.2f} fee={trade.fee:.2f} "
                f"cash_before={trade.cash_before:.2f} position={trade.position_after:.6f}",
                file=file,
            )
    flow = build_cash_flow_summary(result)
    print(
        f"[{algo.name}] cash flow: initial={flow['initial_cash']:.2f} "
        f"in={flow['cash_in']:.2f} out={flow['cash_out']:.2f} fees={flow['total_fees']:.2f} "
        f"final={flow['final_equity']:.2f} pnl={flow['net_pnl']:.2f} "
        f"return={flow['return_pct']:.2f}% buys={flow['buys']} sells={flow['sells']}",
        file=file,
    )


def _resolve_fee_slippage(args: argparse.Namespace, csv_path: Path | None = None) -> tuple[float, float]:
    """Explicit --fee/--slippage win; else --exchange profile; else venue inferred from the CSV name."""
    from traderbot.utils.trading_costs import resolve_cost_rates

    source = csv_path if csv_path is not None else (getattr(args, "csv", None) or getattr(args, "csv_dir", None))
    return resolve_cost_rates(
        exchange=getattr(args, "exchange", None) or None,
        source=source,
        fee=args.fee,
        slippage=args.slippage,
        fee_role=getattr(args, "fee_role", "taker"),
    )


def _run_backtest(
    bars: list[dict],
    strategy_id: str,
    args: argparse.Namespace,
    *,
    csv_path: Path | None = None,
):
    fee, slippage = _resolve_fee_slippage(args, csv_path)
    algo = algorithm_for_id(strategy_id, **_algorithm_kwargs(strategy_id, args, csv_path=csv_path))
    result = run_backtest(
        algo,
        bars,
        initial_cash=args.cash,
        fee_rate=fee,
        slippage_rate=slippage,
        execution=getattr(args, "execution", DEFAULT_BACKTEST_EXECUTION) or DEFAULT_BACKTEST_EXECUTION,
    )
    return algo, result


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Rule-based trading strategies (catalog + backtest).")
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="List reference strategies")
    catalog.add_argument("--implemented", action="store_true")
    catalog.add_argument("--implemented-only", action="store_true", dest="implemented")

    backtest = sub.add_parser("backtest", help="Run long-only backtest on OHLC CSV")
    backtest.add_argument("csv", type=Path)
    backtest.add_argument("--strategy", choices=implemented_strategy_ids(), default="sma_cross")
    backtest.add_argument("--cash", type=float, default=10_000.0)
    _add_fill_flags(backtest)
    backtest.add_argument("--out", type=Path, default=None, help="Write summary JSON + charts")
    add_visualization_flags(backtest)
    _add_vectorbt_flag(backtest)
    _add_param_flags(backtest)

    batch = sub.add_parser("batch", help="Backtest one strategy on every CSV in a directory")
    batch.add_argument("csv_dir", type=Path)
    batch.add_argument("--strategy", choices=implemented_strategy_ids(), default="sma_cross")
    batch.add_argument("--cash", type=float, default=10_000.0)
    _add_fill_flags(batch)
    batch.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Experiment root (default: results/strategies/batch/<strategy>/)",
    )
    batch.add_argument("--min-bars", type=int, default=30)
    add_visualization_flags(batch)
    _add_vectorbt_flag(batch)
    _add_param_flags(batch)

    compare = sub.add_parser(
        "compare",
        help="Backtest every implemented strategy on one OHLC CSV and rank by return",
    )
    compare.add_argument("csv", type=Path)
    compare.add_argument("--cash", type=float, default=10_000.0)
    _add_fill_flags(compare)
    compare.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write per-strategy summaries and compare_manifest.json",
    )
    add_visualization_flags(compare)
    _add_vectorbt_flag(compare)
    _add_param_flags(compare)

    sweep = sub.add_parser(
        "sweep",
        help="Grid-sweep 1-2 params; default selects on validation split (train/val/test)",
    )
    sweep.add_argument("csv", type=Path)
    sweep.add_argument("--strategy", choices=implemented_strategy_ids(), default="sma_cross")
    sweep.add_argument("--cash", type=float, default=10_000.0)
    _add_fill_flags(sweep)
    sweep.add_argument(
        "--param",
        dest="params",
        action="append",
        default=[],
        help="Repeatable: name=v1,v2[,v3] (max 2 --param flags)",
    )
    sweep.add_argument(
        "--selection",
        choices=("validation", "in_sample"),
        default="validation",
        help="validation: pick params on validation window; in_sample: legacy train-only rank",
    )
    sweep.add_argument("--train-fraction", type=float, default=0.6)
    sweep.add_argument("--validation-fraction", type=float, default=0.2)
    sweep.add_argument("--holdout-tail-bars", type=int, default=None)
    sweep.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES, help="Minimum trades (fills) before a combo is eligible (default %(default)s)")
    sweep.add_argument("--max-combos", type=int, default=64)
    sweep.add_argument(
        "--rank-by",
        choices=("edge", "return_pct", "avg_trade_net_pct"),
        default="edge",
        help="edge = significant (t>=2) combos first, then net average per trade (default); return_pct = legacy",
    )
    sweep.add_argument(
        "--optimize-method",
        choices=("grid", "optuna"),
        default="optuna",
        help="grid: 1-2 param sweep; optuna: Bayesian search over all strategy knobs",
    )
    sweep.add_argument("--optimize-n-trials", type=int, default=80)
    sweep.add_argument(
        "--full-grid",
        action="store_true",
        help="Wider built-in ranges (grid lists and Optuna categorical hints)",
    )
    sweep.add_argument("--out", type=Path, default=None, help="Write sweep_manifest.json")
    _add_param_flags(sweep)

    validate = sub.add_parser(
        "validate",
        help="Train/validation/test split; select on validation, report test once",
    )
    validate.add_argument("csv", type=Path)
    validate.add_argument("--strategy", choices=implemented_strategy_ids(), default="sma_cross")
    validate.add_argument("--cash", type=float, default=10_000.0)
    _add_fill_flags(validate)
    validate.add_argument(
        "--param",
        dest="params",
        action="append",
        default=[],
        help="Repeatable: name=v1,v2[,v3] (max 2 --param flags)",
    )
    validate.add_argument("--train-fraction", type=float, default=0.6)
    validate.add_argument("--validation-fraction", type=float, default=0.2)
    validate.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES, help="Minimum trades (fills) before a combo is eligible (default %(default)s)")
    validate.add_argument("--max-combos", type=int, default=64)
    validate.add_argument("--out", type=Path, default=None, help="Write validation_manifest.json")
    _add_param_flags(validate)

    leaderboard = sub.add_parser(
        "leaderboard",
        help="Fetch live 1m bars, tune on train, rank on validation, test top strategies on held-out tail",
    )
    leaderboard.add_argument("--src", default="arb", help="Base asset (Hyperliquid perp coin)")
    leaderboard.add_argument(
        "--resolution",
        default="1",
        help="Hyperliquid candle resolution (1 = 1m)",
    )
    leaderboard.add_argument("--max-bars", type=int, default=2500, help="History length to download")
    leaderboard.add_argument("--cash", type=float, default=10.0)
    _add_fill_flags(leaderboard)
    leaderboard.add_argument("--test-tail-bars", type=int, default=100)
    leaderboard.add_argument("--validation-fraction", type=float, default=0.25)
    leaderboard.add_argument("--top", type=int, default=3, dest="top_n")
    leaderboard.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES, help="Minimum trades (fills) before a combo is eligible (default %(default)s)")
    leaderboard.add_argument("--max-combos", type=int, default=64)
    leaderboard.add_argument(
        "--full-grid",
        action="store_true",
        help="Use expanded per-strategy optimizer grids (more param combos)",
    )
    leaderboard.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write leaderboard_manifest.json and optional CSV under this directory",
    )
    _add_param_flags(leaderboard)

    batch_lb = sub.add_parser(
        "leaderboard-batch",
        help="Leakage-safe leaderboard across many Hyperliquid markets and intervals",
    )
    batch_lb.add_argument(
        "--top-markets",
        type=int,
        default=30,
        help="Number of perp markets (liquid list first, then universe)",
    )
    batch_lb.add_argument(
        "--market",
        dest="markets",
        action="append",
        default=[],
        help="Repeatable extra coin (e.g. arb); added to the batch set",
    )
    batch_lb.add_argument(
        "--resolution",
        dest="resolutions",
        action="append",
        default=[],
        help="Repeatable interval (1,5,15,30,60,240,D); default all Hyperliquid intervals",
    )
    batch_lb.add_argument("--max-bars", type=int, default=2500)
    batch_lb.add_argument("--cash", type=float, default=10.0)
    _add_fill_flags(batch_lb)
    batch_lb.add_argument("--test-tail-bars", type=int, default=100)
    batch_lb.add_argument("--validation-fraction", type=float, default=0.25)
    batch_lb.add_argument("--top", type=int, default=3, dest="top_n")
    batch_lb.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES, help="Minimum trades (fills) before a combo is eligible (default %(default)s)")
    batch_lb.add_argument("--max-combos", type=int, default=128)
    batch_lb.add_argument(
        "--full-grid",
        action="store_true",
        default=True,
        help="Use expanded optimizer grids (default: on)",
    )
    batch_lb.add_argument(
        "--no-full-grid",
        action="store_false",
        dest="full_grid",
        help="Use smaller built-in grids",
    )
    batch_lb.add_argument(
        "--out",
        type=Path,
        default=Path("results/pipelines/leaderboard_batch"),
        help="Batch output root (per market×interval subdirs + batch manifest)",
    )
    _add_param_flags(batch_lb)

    tune = sub.add_parser(
        "tune-defaults",
        help="Average sweeps across assets; write robust defaults + single-run best",
    )
    tune.add_argument("--csv", dest="csvs", action="append", default=[], help="Repeatable OHLC CSV (or pass --csv-dir)")
    tune.add_argument("--csv-dir", type=Path, default=None, help="Use every *.csv in a directory")
    tune.add_argument(
        "--strategy",
        default="all",
        help=f"Strategy id or 'all' ({', '.join(implemented_strategy_ids())})",
    )
    tune.add_argument("--cash", type=float, default=10_000.0)
    _add_fill_flags(tune)
    tune.add_argument(
        "--param",
        dest="params",
        action="append",
        default=[],
        help="Repeatable: name=v1,v2[,v3] (max 2; omit to use built-in grids)",
    )
    tune.add_argument("--holdout-tail-bars", type=int, default=None)
    tune.add_argument("--holdout-fraction", type=float, default=0.2)
    tune.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES, help="Minimum trades (fills) before a combo is eligible (default %(default)s)")
    tune.add_argument("--max-combos", type=int, default=64)
    tune.add_argument("--min-bars", type=int, default=100)
    tune.add_argument("--horizon-label", type=str, default=None)
    tune.add_argument("--out", type=Path, default=None, help="Write tune manifest JSON")
    tune.add_argument(
        "--defaults-out",
        type=Path,
        default=None,
        help="Merge into strategy_defaults.json (default: traderbot/algorithms/strategy_defaults.json)",
    )
    _add_param_flags(tune)

    walk = sub.add_parser(
        "walk-forward",
        help="Rolling tune-on-train / trade-next-window evaluation; reports out-of-sample edge only",
    )
    walk.add_argument("csv", type=Path)
    walk.add_argument("--strategy", choices=implemented_strategy_ids(), default="scalp_dip")
    walk.add_argument("--cash", type=float, default=10_000.0)
    _add_fill_flags(walk)
    walk.add_argument("--param", dest="params", action="append", default=[], help="Repeatable: name=v1,v2")
    walk.add_argument("--train-bars", type=int, default=2000)
    walk.add_argument("--test-bars", type=int, default=500)
    walk.add_argument("--warmup-bars", type=int, default=200)
    walk.add_argument("--min-trades", type=int, default=DEFAULT_MIN_TRADES)
    walk.add_argument("--rank-by", choices=("edge", "return_pct", "avg_trade_net_pct"), default="edge")
    walk.add_argument("--out", type=Path, default=None)
    _add_param_flags(walk)

    args = parser.parse_args(argv)

    if args.command == "walk-forward":
        from traderbot.backtesting import load_bars_csv
        from traderbot.backtesting.sweep import parse_sweep_param
        from traderbot.backtesting.walk_forward import WalkForwardOptions, run_walk_forward

        grid: dict[str, Any] = {}
        try:
            for spec in args.params:
                name, values = parse_sweep_param(spec)
                grid[name] = values
            fee, slippage = _resolve_fee_slippage(args, args.csv)
            payload = run_walk_forward(
                WalkForwardOptions(
                    strategy_id=args.strategy,
                    param_grid=grid,
                    bars=load_bars_csv(args.csv),
                    train_bars=args.train_bars,
                    test_bars=args.test_bars,
                    warmup_bars=args.warmup_bars,
                    cash=args.cash,
                    fee=fee,
                    slippage=slippage,
                    execution=args.execution,
                    min_trades=args.min_trades,
                    rank_by=args.rank_by,
                ),
                base_namespace=args,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(2)
        if args.out is not None:
            args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return

    if args.command == "catalog":
        entries = list_strategies(implemented_only=args.implemented)
        print(json.dumps([asdict(e) for e in entries], indent=2))
        return

    if args.command == "backtest":
        bars = _load_strategy_bars(args.csv, args)
        if not bars:
            print("No bars in CSV", file=sys.stderr)
            sys.exit(1)
        algo, result = _run_backtest(bars, args.strategy, args, csv_path=args.csv)
        summary = backtest_summary_dict(
            algo,
            result,
            bars=len(bars),
            extra={"strategy_id": args.strategy, **_vectorbt_extra(algo, bars, args)},
        )
        print(json.dumps(summary, indent=2))
        sys.stdout.flush()
        _print_run_trade_logs(algo, result)
        if args.out is not None:
            viz = wants_visualization(args, has_out=True)
            save_backtest_result(
                algo,
                result,
                args.out,
                bars=len(bars),
                bar_rows=bars,
                visualize=viz,
                extra={"strategy_id": args.strategy, **_vectorbt_extra(algo, bars, args)},
            )
        return

    if args.command == "batch":
        if not args.csv_dir.is_dir():
            print(f"Not a directory: {args.csv_dir}", file=sys.stderr)
            sys.exit(1)
        batch_root = args.out or default_strategy_batch_out(args.strategy)
        tree = result_tree_at(batch_root, run_id=args.strategy)
        manifest: list[dict[str, Any]] = []
        for csv_path in sorted(args.csv_dir.glob("*.csv")):
            bars = _load_strategy_bars(csv_path, args)
            if len(bars) < args.min_bars:
                continue
            algo, result = _run_backtest(bars, args.strategy, args, csv_path=csv_path)
            vbt_extra = _vectorbt_extra(algo, bars, args)
            run_dir = tree.run_dir_flat(csv_path.stem)
            viz = wants_visualization(args, has_out=True)
            save_backtest_result(
                algo,
                result,
                run_dir,
                bars=len(bars),
                bar_rows=bars,
                visualize=viz,
                extra={
                    "strategy_id": args.strategy,
                    "csv": str(csv_path),
                    **vbt_extra,
                },
            )
            manifest.append(
                {
                    "csv": str(csv_path),
                    "run_dir": str(run_dir),
                    **backtest_summary_dict(
                        algo,
                        result,
                        bars=len(bars),
                        extra=vbt_extra,
                    ),
                }
            )
        manifest_path = tree.reports / "batch_manifest.json"
        manifest_path.write_text(
            json.dumps({"strategy_id": args.strategy, "runs": manifest}, indent=2),
            encoding="utf-8",
        )
        print(json.dumps({"runs": len(manifest), "manifest": str(manifest_path)}, indent=2))
        return

    if args.command == "compare":
        bars = _load_strategy_bars(args.csv, args)
        if not bars:
            print("No bars in CSV", file=sys.stderr)
            sys.exit(1)
        ranked: list[dict[str, Any]] = []
        equity_by_strategy: dict[str, list[tuple[int, float]]] = {}
        compare_root = args.out
        if compare_root is None and wants_visualization(args, has_out=False):
            compare_root = default_strategy_compare_out(args.csv)
        tree = result_tree_at(compare_root, run_id=args.csv.stem) if compare_root is not None else None
        viz = compare_root is not None and wants_visualization(args, has_out=True)
        for strategy_id in backtest_strategy_ids():
            algo, result = _run_backtest(bars, strategy_id, args, csv_path=args.csv)
            equity_by_strategy[strategy_id] = list(result.equity_curve)
            row = backtest_summary_dict(
                algo,
                result,
                bars=len(bars),
                extra={"strategy_id": strategy_id, **_vectorbt_extra(algo, bars, args)},
            )
            ranked.append(row)
            if tree is not None:
                run_dir = tree.run_dir_flat(strategy_id)
                save_backtest_result(
                    algo,
                    result,
                    run_dir,
                    bars=len(bars),
                    bar_rows=bars,
                    visualize=viz,
                    extra={
                        "strategy_id": strategy_id,
                        "csv": str(args.csv),
                        **_vectorbt_extra(algo, bars, args),
                    },
                )
        ranked.sort(key=lambda r: r["return_pct"], reverse=True)
        best = ranked[0] if ranked else None
        payload: dict[str, Any] = {
            "csv": str(args.csv),
            "bars": len(bars),
            "best_strategy_id": best["strategy_id"] if best else None,
            "strategies": ranked,
        }
        if tree is not None:
            if viz:
                try:
                    compare_paths = render_compare_plots(
                        asset_label=args.csv.stem,
                        bars=bars,
                        initial_cash=args.cash,
                        ranked_rows=ranked,
                        equity_by_strategy=equity_by_strategy,
                        out_dir=compare_root,
                    )
                    payload["visualization"] = compare_visualization_paths_to_dict(compare_paths)
                except ImportError:
                    pass
            manifest_path = tree.reports / "compare_manifest.json"
            manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            payload["manifest"] = str(manifest_path)
        print(json.dumps(payload, indent=2))
        return

    if args.command == "sweep":
        from traderbot.backtesting.optimize_select import OptimizeSelectConfig, run_strategy_optimize
        from traderbot.backtesting.sweep import SweepOptions, parse_sweep_param

        param_grid: dict[str, Any] = {}
        if not args.params and args.optimize_method == "grid":
            from traderbot.backtesting.robust_defaults import tune_grid_for_strategy

            param_grid = tune_grid_for_strategy(args.strategy, full=bool(args.full_grid))
        for spec in args.params:
            try:
                name, values = parse_sweep_param(spec)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                sys.exit(2)
            if name in param_grid:
                print(f"duplicate --param {name!r}", file=sys.stderr)
                sys.exit(2)
            param_grid[name] = values
        fee, slippage = _resolve_fee_slippage(args)
        optimize_config = OptimizeSelectConfig(
            selection_mode=args.selection,
            train_fraction=args.train_fraction,
            validation_fraction=args.validation_fraction,
            optimizer_method=args.optimize_method,
            n_trials=int(args.optimize_n_trials),
            full_grid_hints=bool(args.full_grid),
        )
        try:
            payload = run_strategy_optimize(
                SweepOptions(
                    csv_path=args.csv,
                    strategy_id=args.strategy,
                    param_grid=param_grid,
                    cash=args.cash,
                    fee=fee,
                    slippage=slippage,
                    execution=args.execution,
                    holdout_tail_bars=args.holdout_tail_bars,
                    min_trades=args.min_trades,
                    max_combos=args.max_combos,
                    rank_by=getattr(args, "rank_by", "edge"),
                ),
                base_namespace=args,
                config=optimize_config,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(2)
        if args.out is not None:
            out_path = args.out / "sweep_manifest.json" if args.out.is_dir() else args.out
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            payload["manifest"] = str(out_path)
            from traderbot.recording import try_record

            try_record(
                "sweep_session",
                sweep_payload=payload,
                manifest_path=out_path,
            )
        print(json.dumps(payload, indent=2))
        return

    if args.command == "validate":
        from traderbot.backtesting.sweep import parse_sweep_param
        from traderbot.backtesting.validation import ValidationOptions, run_strategy_validation

        if not args.params:
            print("at least one --param name=v1,v2 is required", file=sys.stderr)
            sys.exit(2)
        param_grid: dict[str, Any] = {}
        for spec in args.params:
            try:
                name, values = parse_sweep_param(spec)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                sys.exit(2)
            if name in param_grid:
                print(f"duplicate --param {name!r}", file=sys.stderr)
                sys.exit(2)
            param_grid[name] = values
        fee, slippage = _resolve_fee_slippage(args)
        try:
            payload = run_strategy_validation(
                ValidationOptions(
                    csv_path=str(args.csv),
                    strategy_id=args.strategy,
                    param_grid=param_grid,
                    cash=args.cash,
                    fee=fee,
                    slippage=slippage,
                    execution=args.execution,
                    train_fraction=args.train_fraction,
                    validation_fraction=args.validation_fraction,
                    min_trades=args.min_trades,
                    max_combos=args.max_combos,
                ),
                base_namespace=args,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(2)
        if args.out is not None:
            out_path = args.out / "validation_manifest.json" if args.out.is_dir() else args.out
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            payload["manifest"] = str(out_path)
        print(json.dumps(payload, indent=2))
        return

    if args.command == "leaderboard":
        from traderbot.backtesting.validation import LeaderboardOptions, run_leakage_safe_leaderboard
        from traderbot.data.export import write_csv
        from traderbot.hyperliquid.market_data import fetch_hyperliquid_recent_closed_bars

        try:
            bars = fetch_hyperliquid_recent_closed_bars(
                src=args.src,
                resolution=str(args.resolution),
                max_bars=args.max_bars,
            )
        except Exception as exc:
            print(f"failed to fetch Hyperliquid candles: {exc}", file=sys.stderr)
            sys.exit(1)
        if not bars:
            print("no bars returned from Hyperliquid", file=sys.stderr)
            sys.exit(1)
        label = f"{args.src.upper()}_{args.resolution}m"
        fee, slippage = _resolve_fee_slippage(args)
        payload = run_leakage_safe_leaderboard(
            LeaderboardOptions(
                bars=bars,
                test_tail_bars=args.test_tail_bars,
                validation_fraction_of_pre_test=args.validation_fraction,
                top_n=args.top_n,
                cash=args.cash,
                fee=fee,
                slippage=slippage,
                execution=args.execution,
                min_trades=args.min_trades,
                max_combos=args.max_combos,
                full_grid=bool(getattr(args, "full_grid", False)),
                market_label=label,
            ),
            base_namespace=args,
        )
        payload["source"] = {
            "exchange": "hyperliquid",
            "src": args.src,
            "resolution": str(args.resolution),
            "max_bars_requested": args.max_bars,
            "bars_fetched": len(bars),
        }
        if args.out is not None:
            args.out.mkdir(parents=True, exist_ok=True)
            csv_path = args.out / f"{label}.csv"
            write_csv(csv_path, bars)
            manifest_path = args.out / "leaderboard_manifest.json"
            manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            payload["csv"] = str(csv_path)
            payload["manifest"] = str(manifest_path)
        print(json.dumps(payload, indent=2))
        return

    if args.command == "leaderboard-batch":
        from traderbot.backtesting.leaderboard_batch import (
            LeaderboardBatchOptions,
            default_batch_resolutions,
            resolve_batch_market_coins,
            run_leaderboard_batch,
        )

        if args.markets:
            coins = resolve_batch_market_coins(
                limit=max(args.top_markets, len(args.markets)),
                extra=args.markets,
            )
        else:
            coins = resolve_batch_market_coins(limit=args.top_markets)
        resolutions = args.resolutions or default_batch_resolutions()
        print(
            f"batch: {len(coins)} markets × {len(resolutions)} intervals "
            f"({len(coins) * len(resolutions)} jobs), full_grid={args.full_grid}",
            file=sys.stderr,
            flush=True,
        )
        fee, slippage = _resolve_fee_slippage(args)
        master = run_leaderboard_batch(
            LeaderboardBatchOptions(
                markets=coins,
                resolutions=resolutions,
                out_dir=args.out,
                max_bars=args.max_bars,
                cash=args.cash,
                fee=fee,
                slippage=slippage,
                execution=args.execution,
                test_tail_bars=args.test_tail_bars,
                validation_fraction=args.validation_fraction,
                top_n=args.top_n,
                min_trades=args.min_trades,
                max_combos=args.max_combos,
                full_grid=args.full_grid,
            ),
            log=lambda message: print(message, file=sys.stderr, flush=True),
        )
        print(json.dumps(master, indent=2))
        return

    if args.command == "tune-defaults":
        from traderbot.backtesting.robust_defaults import (
            TuneRobustOptions,
            compare_robust_strategies,
            tune_grid_for_strategy,
            tune_robust_defaults,
            write_robust_defaults_file,
        )
        from traderbot.backtesting.sweep import parse_sweep_param

        csv_paths: list[Path] = [Path(item) for item in (args.csvs or [])]
        if args.csv_dir is not None:
            if not args.csv_dir.is_dir():
                print(f"Not a directory: {args.csv_dir}", file=sys.stderr)
                sys.exit(1)
            csv_paths.extend(sorted(args.csv_dir.glob("*.csv")))
        if not csv_paths:
            print("pass at least one --csv or --csv-dir", file=sys.stderr)
            sys.exit(2)
        if args.horizon_label:
            from traderbot.backtesting.horizon_tune import filter_csv_paths_for_horizon_tuning

            csv_paths = filter_csv_paths_for_horizon_tuning(csv_paths, args.horizon_label)
            if not csv_paths:
                print(
                    f"no CSVs whose bar horizon matches --horizon-label {args.horizon_label!r}",
                    file=sys.stderr,
                )
                sys.exit(2)
        custom_grid: dict[str, Any] = {}
        for spec in args.params or []:
            try:
                name, values = parse_sweep_param(spec)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                sys.exit(2)
            if name in custom_grid:
                print(f"duplicate --param {name!r}", file=sys.stderr)
                sys.exit(2)
            custom_grid[name] = values
        fee, slippage = _resolve_fee_slippage(args)
        if args.strategy == "all":
            if custom_grid:
                print("--param with --strategy all is not supported; tune one strategy at a time", file=sys.stderr)
                sys.exit(2)
            try:
                summary = compare_robust_strategies(
                    csv_paths,
                    cash=args.cash,
                    fee=fee,
                    slippage=slippage,
                    execution=args.execution,
                    holdout_fraction=args.holdout_fraction,
                    min_trades=args.min_trades,
                    horizon_label=args.horizon_label,
                    base_namespace=args,
                )
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                sys.exit(2)
            defaults_target = args.defaults_out or (
                Path(__file__).resolve().parents[1] / "traderbot" / "algorithms" / "strategy_defaults.json"
            )
            write_robust_defaults_file(summary["payloads"], defaults_target)
            if args.out is not None:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print(
                json.dumps(
                    {
                        "recommended_strategy_id": summary["recommended_strategy_id"],
                        "ranking": summary["ranking"],
                        "failures": summary["failures"],
                        "defaults_out": str(defaults_target),
                    },
                    indent=2,
                )
            )
            return
        if args.strategy not in implemented_strategy_ids():
            print(f"unknown strategy: {args.strategy}", file=sys.stderr)
            sys.exit(2)
        try:
            grid = custom_grid or tune_grid_for_strategy(args.strategy)
            tuned = tune_robust_defaults(
                TuneRobustOptions(
                    csv_paths=csv_paths,
                    strategy_id=args.strategy,
                    param_grid=grid,
                    cash=args.cash,
                    fee=fee,
                    slippage=slippage,
                    execution=args.execution,
                    holdout_tail_bars=args.holdout_tail_bars,
                    holdout_fraction=args.holdout_fraction,
                    min_trades=args.min_trades,
                    max_combos=args.max_combos,
                    horizon_label=args.horizon_label,
                    min_bars=args.min_bars,
                ),
                args,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            sys.exit(2)
        defaults_target = args.defaults_out or (
            Path(__file__).resolve().parents[1] / "traderbot" / "algorithms" / "strategy_defaults.json"
        )
        write_robust_defaults_file({args.strategy: tuned}, defaults_target)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(tuned, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "strategy_id": tuned["strategy_id"],
                    "robust_params": tuned["robust_params"],
                    "robust_metrics": tuned["robust_metrics"],
                    "best_params": tuned["best_params"],
                    "per_asset_best": tuned["per_asset_best"],
                    "defaults_out": str(defaults_target),
                },
                indent=2,
            )
        )
        return
