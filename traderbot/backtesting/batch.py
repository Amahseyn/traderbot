from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from traderbot.algorithms.registry import (
    algorithm_for_id,
    strategy_kwargs_from_namespace,
)
from traderbot.backtesting import (
    backtest_summary_dict,
    load_bars_csv,
    run_backtest,
    save_backtest_result,
    vectorbt_extra_for_backtest,
)
from traderbot.data.intrahour import enrich_bars_for_csv
from traderbot.results.layout import default_strategy_batch_out, result_tree_at


@dataclass
class StrategyBatchOptions:
    csv_dir: Path
    strategy_id: str
    out_dir: Path | None = None
    cash: float = 10_000.0
    fee: float = 0.0
    slippage: float = 0.0
    execution: str = "close"
    min_bars: int = 30
    visualize: bool = False
    vectorbt: bool = False
    strategy_namespace: Any | None = None


def run_strategy_batch(options: StrategyBatchOptions) -> dict[str, Any]:
    """Backtest one strategy on every ``*.csv`` in a directory."""
    csv_dir = options.csv_dir.resolve()
    if not csv_dir.is_dir():
        raise NotADirectoryError(f"Not a directory: {csv_dir}")

    from traderbot.algorithms.cli_args import default_strategy_namespace

    namespace = options.strategy_namespace or default_strategy_namespace()
    batch_root = options.out_dir or default_strategy_batch_out(options.strategy_id)
    tree = result_tree_at(batch_root, run_id=options.strategy_id)
    manifest: list[dict[str, Any]] = []
    for csv_path in sorted(csv_dir.glob("*.csv")):
        bars = enrich_bars_for_csv(load_bars_csv(csv_path), csv_path, namespace)
        if len(bars) < options.min_bars:
            continue
        kwargs = strategy_kwargs_from_namespace(options.strategy_id, namespace)
        algo = algorithm_for_id(options.strategy_id, **kwargs)
        result = run_backtest(
            algo,
            bars,
            initial_cash=options.cash,
            fee_rate=options.fee,
            slippage_rate=options.slippage,
            execution=options.execution,
        )
        vbt_extra = (
            vectorbt_extra_for_backtest(
                algo,
                bars,
                initial_cash=options.cash,
                fee_rate=options.fee,
            )
            or {}
            if options.vectorbt
            else {}
        )
        run_dir = tree.run_dir_flat(csv_path.stem)
        save_backtest_result(
            algo,
            result,
            run_dir,
            bars=len(bars),
            bar_rows=bars,
            visualize=options.visualize,
            extra={
                "strategy_id": options.strategy_id,
                "csv": str(csv_path),
                **vbt_extra,
            },
        )
        manifest.append(
            {
                "csv": str(csv_path),
                "run_dir": str(run_dir),
                **backtest_summary_dict(algo, result, bars=len(bars), extra=vbt_extra),
            }
        )
    manifest_path = tree.reports / "batch_manifest.json"
    payload = {"strategy_id": options.strategy_id, "runs": manifest}
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"runs": len(manifest), "manifest": str(manifest_path), "batch_root": str(batch_root)}
