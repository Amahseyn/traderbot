from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from traderbot.algorithms.registry import (
    algorithm_for_id,
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
    extra = vectorbt_extra_for_backtest(
        algo,
        bars,
        initial_cash=args.cash,
        fee_rate=args.fee,
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


def _run_backtest(
    bars: list[dict],
    strategy_id: str,
    args: argparse.Namespace,
):
    algo = algorithm_for_id(strategy_id, **strategy_kwargs_from_namespace(strategy_id, args))
    result = run_backtest(algo, bars, initial_cash=args.cash, fee_rate=args.fee)
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
    backtest.add_argument("--fee", type=float, default=0.0)
    backtest.add_argument("--out", type=Path, default=None, help="Write summary JSON + charts")
    add_visualization_flags(backtest)
    _add_vectorbt_flag(backtest)
    _add_param_flags(backtest)

    batch = sub.add_parser("batch", help="Backtest one strategy on every CSV in a directory")
    batch.add_argument("csv_dir", type=Path)
    batch.add_argument("--strategy", choices=implemented_strategy_ids(), default="sma_cross")
    batch.add_argument("--cash", type=float, default=10_000.0)
    batch.add_argument("--fee", type=float, default=0.0)
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
    compare.add_argument("--fee", type=float, default=0.0)
    compare.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write per-strategy summaries and compare_manifest.json",
    )
    add_visualization_flags(compare)
    _add_vectorbt_flag(compare)
    _add_param_flags(compare)

    args = parser.parse_args(argv)

    if args.command == "catalog":
        entries = list_strategies(implemented_only=args.implemented)
        print(json.dumps([asdict(e) for e in entries], indent=2))
        return

    if args.command == "backtest":
        bars = _load_strategy_bars(args.csv, args)
        if not bars:
            print("No bars in CSV", file=sys.stderr)
            sys.exit(1)
        algo, result = _run_backtest(bars, args.strategy, args)
        summary = backtest_summary_dict(
            algo,
            result,
            bars=len(bars),
            extra={"strategy_id": args.strategy, **_vectorbt_extra(algo, bars, args)},
        )
        print(json.dumps(summary, indent=2))
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
            algo, result = _run_backtest(bars, args.strategy, args)
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
        for strategy_id in implemented_strategy_ids():
            algo, result = _run_backtest(bars, strategy_id, args)
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
