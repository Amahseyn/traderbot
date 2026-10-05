from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from traderbot.algorithms.cli_args import default_strategy_namespace, merge_strategy_namespace
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.backtesting import backtest_summary_dict, load_bars_csv, run_backtest
from traderbot.backtesting.holdout_window import return_pct_over_equity_tail
from traderbot.data.intrahour import enrich_bars_for_csv

MAX_SWEEP_PARAMS = 2
DEFAULT_MAX_COMBOS = 64


def parse_sweep_param(spec: str) -> tuple[str, list[Any]]:
    """Parse ``name=v1,v2[,v3]`` into a param name and typed values."""
    name, sep, raw_values = spec.partition("=")
    name = name.strip()
    if not name or not sep:
        raise ValueError(f"invalid --param {spec!r}; expected name=v1,v2")
    values = [_parse_scalar(item) for item in raw_values.split(",") if item.strip() != ""]
    if not values:
        raise ValueError(f"invalid --param {spec!r}; no values")
    allowed = set(vars(default_strategy_namespace()))
    if name not in allowed:
        raise ValueError(f"unknown sweep param {name!r}")
    return name, values


def _parse_scalar(text: str) -> Any:
    cleaned = text.strip()
    lowered = cleaned.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(cleaned)
    except ValueError:
        pass
    try:
        return float(cleaned)
    except ValueError:
        pass
    return cleaned


@dataclass
class SweepOptions:
    csv_path: Path
    strategy_id: str
    param_grid: dict[str, list[Any]]
    cash: float = 10_000.0
    fee: float = 0.0
    slippage: float = 0.0
    execution: str = "close"
    holdout_tail_bars: int | None = None
    min_trades: int = 0
    max_combos: int = DEFAULT_MAX_COMBOS


@dataclass
class SweepResult:
    payload: dict[str, Any] = field(default_factory=dict)


def run_strategy_sweep(options: SweepOptions, base_namespace: Any | None = None) -> dict[str, Any]:
    """Run a small coordinate grid (1-2 params) and rank by holdout or full return."""
    if not options.param_grid or len(options.param_grid) > MAX_SWEEP_PARAMS:
        raise ValueError(f"sweep requires 1-{MAX_SWEEP_PARAMS} params")
    combos = list(itertools.product(*options.param_grid.values()))
    if not combos:
        raise ValueError("sweep param grid is empty")
    if len(combos) > options.max_combos:
        raise ValueError(f"sweep has {len(combos)} combos; max is {options.max_combos}")
    if options.holdout_tail_bars is not None and options.holdout_tail_bars < 1:
        raise ValueError("holdout_tail_bars must be >= 1")
    if options.min_trades < 0:
        raise ValueError("min_trades must be >= 0")

    base = merge_strategy_namespace(base_namespace)
    csv_path = Path(options.csv_path)
    bars = enrich_bars_for_csv(load_bars_csv(csv_path), csv_path, base)
    if not bars:
        raise ValueError(f"No bars in CSV: {csv_path}")

    names = list(options.param_grid.keys())
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for combo in combos:
        namespace = merge_strategy_namespace(base)
        params = dict(zip(names, combo))
        for key, value in params.items():
            setattr(namespace, key, value)
        try:
            algo = algorithm_for_id(options.strategy_id, **strategy_kwargs_from_namespace(options.strategy_id, namespace))
            result = run_backtest(
                algo,
                bars,
                initial_cash=options.cash,
                fee_rate=options.fee,
                slippage_rate=options.slippage,
                execution=options.execution,
            )
        except ValueError as exc:
            skipped.append({"params": params, "error": str(exc)})
            continue
        holdout_return = None
        if options.holdout_tail_bars is not None:
            holdout_return = return_pct_over_equity_tail(list(result.equity_curve), options.holdout_tail_bars)
        row = backtest_summary_dict(
            algo,
            result,
            bars=len(bars),
            extra={"strategy_id": options.strategy_id, "params": params},
        )
        row["holdout_return_pct"] = holdout_return
        row["eligible"] = row["trades"] >= options.min_trades
        rows.append(row)
    if not rows:
        reason = skipped[0]["error"] if skipped else "no combinations"
        raise ValueError(f"sweep found no valid combos: {reason}")

    rank_by = "holdout_return_pct" if options.holdout_tail_bars is not None else "return_pct"

    def _rank_key(row: dict[str, Any]) -> tuple[int, float]:
        metric = row.get(rank_by)
        return (1 if row["eligible"] else 0, float(metric) if metric is not None else float("-inf"))

    rows.sort(key=_rank_key, reverse=True)
    best = rows[0] if rows else None
    return {
        "csv": str(csv_path),
        "strategy_id": options.strategy_id,
        "bars": len(bars),
        "cash": options.cash,
        "fee": options.fee,
        "slippage": options.slippage,
        "execution": options.execution,
        "holdout_tail_bars": options.holdout_tail_bars,
        "min_trades": options.min_trades,
        "rank_by": rank_by,
        "param_grid": {name: list(values) for name, values in options.param_grid.items()},
        "combinations": len(rows),
        "skipped": skipped,
        "best_params": dict(best["params"]) if best else None,
        "best": best,
        "rows": rows,
    }
