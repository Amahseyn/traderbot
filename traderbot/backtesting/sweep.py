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
from traderbot.utils.trading_costs import (
    DEFAULT_BACKTEST_EXECUTION,
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_TRADE_FEE_RATE,
)

MAX_SWEEP_PARAMS = 2
DEFAULT_MAX_COMBOS = 64
DEFAULT_LIVE_TUNE_MAX_BARS = 100
DEFAULT_LIVE_TUNE_HOLDOUT_BARS = 20


def sweep_rank_key(row: dict[str, Any], *, rank_by: str = "return_pct") -> tuple[int, float]:
    """Rank eligible combos by the in-sample metric only.

    ``holdout_return_pct`` is reported for inspection but deliberately excluded
    from the sort key so holdout data never influences parameter selection.
    """
    primary = row.get(rank_by)
    return (
        1 if row.get("eligible") else 0,
        float(primary) if primary is not None else float("-inf"),
    )


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
    strategy_id: str
    param_grid: dict[str, list[Any]]
    csv_path: Path | None = None
    bars: list[dict[str, Any]] | None = None
    cash: float = 10_000.0
    fee: float = DEFAULT_TRADE_FEE_RATE
    slippage: float = DEFAULT_SLIPPAGE_RATE
    execution: str = DEFAULT_BACKTEST_EXECUTION
    holdout_tail_bars: int | None = None
    min_trades: int = 0
    max_combos: int = DEFAULT_MAX_COMBOS
    max_bars: int | None = None


@dataclass
class SweepResult:
    payload: dict[str, Any] = field(default_factory=dict)


def run_strategy_sweep(options: SweepOptions, base_namespace: Any | None = None) -> dict[str, Any]:
    """Run a small coordinate grid (1-2 params) and rank on the training window.

    When ``holdout_tail_bars`` is set, combos are fit on leading bars only; ``holdout_return_pct``
    is reported for comparison but is not used to select parameters (avoids holdout peeking).
    """
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
    if options.bars is not None:
        bars = list(options.bars)
        csv_path = (
            Path(options.csv_path)
            if options.csv_path is not None
            else Path(f"nobitex://{options.strategy_id}")
        )
    else:
        if options.csv_path is None:
            raise ValueError("sweep requires csv_path or preloaded bars")
        csv_path = Path(options.csv_path)
        bars = enrich_bars_for_csv(load_bars_csv(csv_path), csv_path, base)
        if not bars:
            raise ValueError(f"No bars in CSV: {csv_path}")
    if options.max_bars is not None:
        if options.max_bars < 2:
            raise ValueError("max_bars must be at least 2")
        if len(bars) > options.max_bars:
            bars = bars[-options.max_bars :]

    holdout_bars = options.holdout_tail_bars
    train_bars = bars
    if holdout_bars is not None:
        if len(bars) <= holdout_bars:
            raise ValueError(
                f"holdout_tail_bars={holdout_bars} requires more than {holdout_bars} bars (got {len(bars)})"
            )
        train_bars = bars[:-holdout_bars]

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
                train_bars,
                initial_cash=options.cash,
                fee_rate=options.fee,
                slippage_rate=options.slippage,
                execution=options.execution,
            )
        except ValueError as exc:
            skipped.append({"params": params, "error": str(exc)})
            continue
        holdout_return = None
        if holdout_bars is not None:
            full_algo = algorithm_for_id(
                options.strategy_id,
                **strategy_kwargs_from_namespace(options.strategy_id, namespace),
            )
            full_result = run_backtest(
                full_algo,
                bars,
                initial_cash=options.cash,
                fee_rate=options.fee,
                slippage_rate=options.slippage,
                execution=options.execution,
            )
            holdout_return = return_pct_over_equity_tail(
                list(full_result.equity_curve),
                holdout_bars,
            )
        row = backtest_summary_dict(
            algo,
            result,
            bars=len(train_bars),
            extra={"strategy_id": options.strategy_id, "params": params},
        )
        row["holdout_return_pct"] = holdout_return
        row["eligible"] = row["trades"] >= options.min_trades
        rows.append(row)
    if not rows:
        reason = skipped[0]["error"] if skipped else "no combinations"
        raise ValueError(f"sweep found no valid combos: {reason}")

    rank_by = "return_pct"

    for row in rows:
        holdout_return = row.get("holdout_return_pct")
        row["holdout_losing"] = (
            holdout_return is not None and float(holdout_return) < 0.0
        )

    def _rank_key(row: dict[str, Any]) -> tuple[int, float]:
        return sweep_rank_key(row, rank_by=rank_by)

    rows.sort(key=_rank_key, reverse=True)
    best = rows[0] if rows else None

    from traderbot.backtesting.bar_windows import (
        fit_window_utc_from_bars,
        infer_bar_minutes,
        sample_window_utc_from_bars,
    )

    if options.csv_path is not None:
        try:
            from traderbot.utils.resolution import resolution_from_csv_path, resolution_minutes

            bar_minutes = resolution_minutes(resolution_from_csv_path(Path(options.csv_path).name)) or 60
        except (ValueError, IndexError):
            bar_minutes = infer_bar_minutes(bars)
    else:
        bar_minutes = infer_bar_minutes(bars)
    optimize_start_utc, optimize_end_utc = fit_window_utc_from_bars(
        bars,
        bar_minutes=bar_minutes,
        holdout_tail_bars=holdout_bars,
    )
    sample_start_utc, sample_end_utc = sample_window_utc_from_bars(bars, bar_minutes=bar_minutes)
    holdout_start_utc = None
    holdout_end_utc = None
    if holdout_bars is not None and len(bars) > holdout_bars:
        holdout_slice = bars[-holdout_bars:]
        holdout_start_utc, holdout_end_utc = sample_window_utc_from_bars(holdout_slice, bar_minutes=bar_minutes)

    return {
        "csv": str(csv_path),
        "strategy_id": options.strategy_id,
        "bars": len(bars),
        "bar_minutes": bar_minutes,
        "optimize_start_utc": optimize_start_utc,
        "optimize_end_utc": optimize_end_utc,
        "sample_start_utc": sample_start_utc,
        "sample_end_utc": sample_end_utc,
        "holdout_start_utc": holdout_start_utc,
        "holdout_end_utc": holdout_end_utc,
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
