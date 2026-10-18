from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.algorithms.registry import backtest_strategy_ids
from traderbot.backtesting import load_bars_csv
from traderbot.backtesting.sweep import SweepOptions
from traderbot.utils.resolution import resolution_from_csv_path
from traderbot.utils.trading_costs import (
    ResolvesCostRates,
    DEFAULT_BACKTEST_EXECUTION,
)

MIN_TUNE_BARS = 100
DEFAULT_HOLDOUT_FRACTION = 0.2
from traderbot.backtesting.trade_stats import DEFAULT_MIN_TRADES  # noqa: E402  (30)

DEFAULT_TUNE_GRIDS: dict[str, dict[str, list[Any]]] = {
    "sma_cross": {"fast": [5, 10, 20], "slow": [20, 50, 100]},
    "ema_cross": {"fast": [5, 10, 20], "slow": [20, 50, 100]},
    "finrl_ema_intraday": {"fast": [8, 12, 16], "slow": [36, 48, 60]},
    "rsi_threshold": {"period": [7, 14, 21], "oversold": [20, 30.0]},
    "macd_cross": {"fast": [8, 12], "slow": [21, 26]},
    "bollinger_mean_reversion": {"period": [14, 20, 30], "num_std": [1.5, 2.0, 2.5]},
    "chart_patterns": {"swing_window_bars": [2, 3, 5], "pattern_score_threshold": [0.25, 0.35, 0.5]},
    "breakout_atr": {"lookback_bars": [10, 20, 40], "atr_multiplier": [1.0, 1.5, 2.0]},
    "ma_trend": {"trend_fast_period": [20, 50], "trend_slow_period": [100, 200]},
    "rsi_trend": {"rsi_trend_entry": [50, 55, 60], "rsi_trend_exit": [40, 45]},
    "rsi_divergence": {"swing_window_bars": [2, 3, 5], "divergence_rsi_level": [35, 40, 45]},
    "range_breakout": {"lookback_bars": [10, 20, 40], "range_max_width_pct": [0.03, 0.06, 0.1]},
    "scalp_dip": {"dip_pct": [0.003, 0.005, 0.008], "take_profit_pct": [0.005, 0.0075, 0.01]},
    "dca": {"dca_interval_bars": [6, 24, 72], "dca_order_count": [5, 10, 20]},
    "grid": {"grid_range_pct": [0.03, 0.05, 0.1], "grid_levels": [4, 6, 10]},
    "spot_grid": {"grid_count": [4, 6, 8], "grid_take_profit_pct": [0.008, 0.01, 0.012]},
    "perp_market_making": {
        "mm_half_spread_pct": [0.0003, 0.0005, 0.0008],
        "mm_inventory_skew": [0.0, 0.25],
    },
    "momentum_shock": {"shock_return_std": [2.0, 2.5, 3.0], "shock_hold_bars": [6, 12, 24]},
    "online_logistic": {"ml_horizon_bars": [3, 6, 12], "ml_buy_threshold": [0.52, 0.55, 0.6]},
    "ensemble": {
        "ensemble_preset": ["1m_scalp_trend", "1m_pattern_ma", "intraday_trend_stack"],
        "ensemble_entry_rule": ["all", "majority"],
    },
}

FULL_TUNE_GRIDS: dict[str, dict[str, list[Any]]] = {
    "sma_cross": {"fast": [3, 5, 8, 10, 12, 15, 20], "slow": [15, 20, 30, 50, 80, 100]},
    "ema_cross": {"fast": [3, 5, 8, 10, 12, 15, 20], "slow": [15, 20, 30, 50, 80, 100]},
    "finrl_ema_intraday": {"fast": [6, 8, 10, 12, 16, 20], "slow": [24, 36, 48, 60, 96]},
    "rsi_threshold": {"period": [5, 7, 10, 14, 21], "oversold": [15, 20, 25, 30.0]},
    "macd_cross": {"fast": [6, 8, 10, 12, 15], "slow": [18, 21, 26, 30, 34]},
    "bollinger_mean_reversion": {
        "period": [10, 14, 20, 30, 40],
        "num_std": [1.25, 1.5, 2.0, 2.5, 3.0],
    },
    "chart_patterns": {
        "swing_window_bars": [2, 3, 4, 5, 7],
        "pattern_score_threshold": [0.2, 0.25, 0.35, 0.45, 0.55],
    },
    "breakout_atr": {
        "lookback_bars": [8, 10, 15, 20, 30, 40],
        "atr_multiplier": [0.75, 1.0, 1.25, 1.5, 2.0, 2.5],
    },
    "ma_trend": {"trend_fast_period": [10, 20, 30, 50, 80], "trend_slow_period": [100, 150, 200, 250]},
    "rsi_trend": {"rsi_trend_entry": [50, 52, 55, 58, 60, 65], "rsi_trend_exit": [35, 40, 45, 48]},
    "rsi_divergence": {"swing_window_bars": [2, 3, 4, 5, 7], "divergence_rsi_level": [30, 35, 40, 45, 50]},
    "range_breakout": {"lookback_bars": [8, 12, 16, 20, 30, 40], "range_max_width_pct": [0.02, 0.03, 0.05, 0.08, 0.12]},
    "scalp_dip": {"dip_pct": [0.002, 0.003, 0.004, 0.006, 0.008, 0.012], "take_profit_pct": [0.005, 0.0065, 0.0075, 0.009, 0.01]},
    "dca": {"dca_interval_bars": [1, 6, 12, 24, 48, 72, 168], "dca_order_count": [4, 8, 12, 24]},
    "grid": {"grid_range_pct": [0.02, 0.03, 0.05, 0.08, 0.12], "grid_levels": [3, 4, 6, 8, 12]},
    "spot_grid": {
        "grid_count": [3, 4, 6, 8, 10],
        "grid_take_profit_pct": [0.006, 0.008, 0.01, 0.012, 0.018],
    },
    "perp_market_making": {
        "mm_half_spread_pct": [0.0002, 0.0003, 0.0005, 0.0008, 0.0012],
        "mm_inventory_skew": [0.0, 0.15, 0.25, 0.4, 0.5],
    },
    "momentum_shock": {"shock_return_std": [1.5, 2.0, 2.5, 3.0, 3.5], "shock_hold_bars": [3, 6, 12, 24, 48]},
    "online_logistic": {"ml_horizon_bars": [1, 3, 6, 12, 24], "ml_buy_threshold": [0.5, 0.52, 0.55, 0.58, 0.62]},
    "ensemble": {
        "ensemble_preset": ["1m_scalp_trend", "1m_pattern_ma", "1m_ml_trend", "intraday_trend_stack"],
        "ensemble_entry_rule": ["all", "majority", "primary"],
    },
}


@dataclass
class TuneRobustOptions(ResolvesCostRates):
    csv_paths: list[Path]
    strategy_id: str
    param_grid: dict[str, list[Any]] = field(default_factory=dict)
    cash: float = 10_000.0
    fee: float | None = None
    slippage: float | None = None
    exchange: str | None = None
    execution: str = DEFAULT_BACKTEST_EXECUTION
    holdout_tail_bars: int | None = None
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION
    min_trades: int = DEFAULT_MIN_TRADES
    max_combos: int = 64
    horizon_label: str | None = None
    resolution: str | None = None
    min_bars: int = MIN_TUNE_BARS


def tune_grid_for_strategy(strategy_id: str, *, full: bool = False) -> dict[str, list[Any]]:
    """Built-in grid for one strategy (used when the caller passes no --param)."""
    source = FULL_TUNE_GRIDS if full else DEFAULT_TUNE_GRIDS
    grid = source.get(strategy_id)
    if grid is None:
        raise ValueError(f"no built-in tune grid for strategy_id={strategy_id!r}")
    return {name: list(values) for name, values in grid.items()}


def validate_tune_grids(*, full: bool = False) -> None:
    """Raise if any backtest strategy is missing a grid or uses non-strategy param names."""
    from traderbot.algorithms.registry import backtest_strategy_ids, strategy_param_names

    source = FULL_TUNE_GRIDS if full else DEFAULT_TUNE_GRIDS
    for strategy_id in backtest_strategy_ids():
        grid = source.get(strategy_id)
        if grid is None:
            raise ValueError(f"missing tune grid for strategy_id={strategy_id!r}")
        if not grid:
            raise ValueError(f"empty tune grid for strategy_id={strategy_id!r}")
        if len(grid) > 2:
            raise ValueError(f"tune grid for {strategy_id!r} has more than 2 params")
        allowed = set(strategy_param_names(strategy_id))
        for name in grid:
            if name not in allowed:
                raise ValueError(f"tune grid param {name!r} is not used by strategy {strategy_id!r}")


def _holdout_for_bar_count(bar_count: int, options: TuneRobustOptions) -> int | None:
    if options.holdout_tail_bars is not None:
        return options.holdout_tail_bars
    if options.holdout_fraction <= 0:
        return None
    return max(1, int(bar_count * options.holdout_fraction))


def _combo_key(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, default=str)


def tune_robust_defaults(options: TuneRobustOptions, base_namespace: Any | None = None) -> dict[str, Any]:
    """Sweep one strategy on every CSV, then average each combo across assets.

    The robust default is the combo with the best *mean* metric across assets
    (not the mean of the parameter values). ``best`` keeps the single-run
    winner separately so callers can tell robust apart from lucky.
    """
    if not options.csv_paths:
        raise ValueError("tune_robust_defaults requires at least one csv_path")
    param_grid = dict(options.param_grid) or tune_grid_for_strategy(options.strategy_id)
    if len(param_grid) > 2:
        raise ValueError("tune grid requires 1-2 params")
    if options.strategy_id not in backtest_strategy_ids():
        raise ValueError(f"unsupported strategy_id={options.strategy_id!r}")

    base = default_strategy_namespace() if base_namespace is None else base_namespace
    per_asset: list[dict[str, Any]] = []
    skipped_assets: list[dict[str, Any]] = []
    for csv_path in options.csv_paths:
        try:
            bar_count = len(load_bars_csv(Path(csv_path)))
        except (OSError, ValueError) as exc:
            skipped_assets.append({"csv": str(csv_path), "reason": str(exc)})
            continue
        if bar_count < options.min_bars:
            skipped_assets.append({"csv": str(csv_path), "reason": f"only {bar_count} bars < min_bars {options.min_bars}"})
            continue
        from traderbot.backtesting.optimize_select import OptimizeSelectConfig, run_strategy_optimize

        payload = run_strategy_optimize(
            SweepOptions(
                csv_path=Path(csv_path),
                strategy_id=options.strategy_id,
                param_grid={name: list(values) for name, values in param_grid.items()},
                cash=options.cash,
                fee=options.fee,
                slippage=options.slippage,
                execution=options.execution,
                holdout_tail_bars=_holdout_for_bar_count(bar_count, options),
                min_trades=options.min_trades,
                max_combos=options.max_combos,
            ),
            base,
            config=OptimizeSelectConfig(selection_mode="validation"),
        )
        per_asset.append(payload)
    if not per_asset:
        raise ValueError("tune_robust_defaults found no usable CSVs")

    rank_by = per_asset[0]["rank_by"]
    aggregated: dict[str, dict[str, Any]] = {}
    for payload in per_asset:
        for row in payload["rows"]:
            key = _combo_key(dict(row["params"]))
            entry = aggregated.setdefault(key, {"params": dict(row["params"]), "samples": []})
            metric = row.get(rank_by)
            entry["samples"].append(
                {
                    "csv": payload["csv"],
                    "metric": metric,
                    "eligible": bool(row.get("eligible")),
                    "trades": row.get("trades"),
                    "return_pct": row.get("return_pct"),
                }
            )
    rows: list[dict[str, Any]] = []
    for entry in aggregated.values():
        eligible_metrics = [
            float(sample["metric"])
            for sample in entry["samples"]
            if sample["eligible"] and sample["metric"] is not None
        ]
        eligible_assets = len(
            {sample["csv"] for sample in entry["samples"] if sample["eligible"] and sample["metric"] is not None}
        )
        total_trades = sum(int(sample["trades"] or 0) for sample in entry["samples"])
        if eligible_metrics:
            mean_metric = statistics.fmean(eligible_metrics)
            median_metric = statistics.median(eligible_metrics)
            worst_metric = min(eligible_metrics)
        else:
            mean_metric = float("-inf")
            median_metric = float("-inf")
            worst_metric = float("-inf")
        rows.append(
            {
                "params": entry["params"],
                "assets": len(entry["samples"]),
                "eligible_assets": eligible_assets,
                "total_trades": total_trades,
                "mean_metric": mean_metric,
                "median_metric": median_metric,
                "worst_metric": worst_metric,
                "samples": entry["samples"],
            }
        )

    def _robust_key(row: dict[str, Any]) -> tuple[int, float, float, float, int]:
        return (
            int(row["eligible_assets"]),
            float(row["mean_metric"]),
            float(row["median_metric"]),
            float(row["worst_metric"]),
            int(row["total_trades"]),
        )

    rows.sort(key=_robust_key, reverse=True)
    robust = rows[0]

    best_row: dict[str, Any] | None = None
    best_csv: str | None = None
    for payload in per_asset:
        for row in payload["rows"]:
            metric = row.get(rank_by)
            if metric is None:
                continue
            if best_row is None:
                best_row, best_csv = row, payload["csv"]
                continue
            current = (1 if best_row.get("eligible") else 0, float(best_row.get(rank_by)))  # type: ignore[arg-type]
            challenger = (1 if row.get("eligible") else 0, float(metric))
            if challenger > current:
                best_row, best_csv = row, payload["csv"]

    first_csv = Path(per_asset[0]["csv"])
    if options.resolution is not None:
        resolution = options.resolution
    else:
        try:
            resolution = resolution_from_csv_path(first_csv.name)
        except (IndexError, ValueError):
            resolution = None
    resolutions = sorted(
        {resolution_from_csv_path(Path(payload["csv"]).name) for payload in per_asset if "_" in Path(payload["csv"]).name}
    )
    return {
        "strategy_id": options.strategy_id,
        "resolution": resolution if len(resolutions) <= 1 else None,
        "resolutions": resolutions,
        "horizon_label": options.horizon_label,
        "assets": [payload["csv"] for payload in per_asset],
        "asset_count": len(per_asset),
        "skipped_assets": skipped_assets,
        "rank_by": rank_by,
        "param_grid": {name: list(values) for name, values in param_grid.items()},
        "min_trades": options.min_trades,
        "cash": options.cash,
        "fee": options.fee,
        "combinations": len(rows),
        "robust_params": dict(robust["params"]),
        "robust_metrics": {
            "mean_metric": robust["mean_metric"],
            "median_metric": robust["median_metric"],
            "worst_metric": robust["worst_metric"],
            "eligible_assets": robust["eligible_assets"],
            "total_trades": robust["total_trades"],
        },
        "robust": robust,
        "best_params": dict(best_row["params"]) if best_row is not None else None,
        "best": {**(best_row or {}), "csv": best_csv} if best_row is not None else None,
        "per_asset_best": [
            {"csv": payload["csv"], "best_params": payload.get("best_params"), "best": payload.get("best")}
            for payload in per_asset
        ],
        "rows": rows,
    }


def compare_robust_strategies(
    csv_paths: list[Path],
    *,
    strategy_ids: list[str] | None = None,
    grids_by_strategy: dict[str, dict[str, list[Any]]] | None = None,
    cash: float = 10_000.0,
    fee: float | None = None,
    slippage: float | None = None,
    execution: str = DEFAULT_BACKTEST_EXECUTION,
    holdout_fraction: float = DEFAULT_HOLDOUT_FRACTION,
    min_trades: int = DEFAULT_MIN_TRADES,
    horizon_label: str | None = None,
    base_namespace: Any | None = None,
) -> dict[str, Any]:
    """Tune every strategy on the same CSVs and rank by robust mean metric."""
    targets = list(strategy_ids) if strategy_ids else backtest_strategy_ids()
    ranking: list[dict[str, Any]] = []
    payloads: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    for strategy_id in targets:
        grid = dict((grids_by_strategy or {}).get(strategy_id) or tune_grid_for_strategy(strategy_id))
        try:
            payload = tune_robust_defaults(
                TuneRobustOptions(
                    csv_paths=list(csv_paths),
                    strategy_id=strategy_id,
                    param_grid=grid,
                    cash=cash,
                    fee=fee,
                    slippage=slippage,
                    execution=execution,
                    holdout_fraction=holdout_fraction,
                    min_trades=min_trades,
                    horizon_label=horizon_label,
                ),
                base_namespace,
            )
        except ValueError as exc:
            failures.append({"strategy_id": strategy_id, "error": str(exc)})
            continue
        payloads[strategy_id] = payload
        ranking.append(
            {
                "strategy_id": strategy_id,
                "robust_params": payload["robust_params"],
                "mean_metric": payload["robust_metrics"]["mean_metric"],
                "median_metric": payload["robust_metrics"]["median_metric"],
                "eligible_assets": payload["robust_metrics"]["eligible_assets"],
                "asset_count": payload["asset_count"],
            }
        )
    ranking.sort(
        key=lambda row: (int(row["eligible_assets"]), float(row["mean_metric"]), float(row["median_metric"])),
        reverse=True,
    )
    return {
        "horizon_label": horizon_label,
        "assets": [str(path) for path in csv_paths],
        "rank_by": next((payload["rank_by"] for payload in payloads.values()), None),
        "recommended_strategy_id": ranking[0]["strategy_id"] if ranking else None,
        "ranking": ranking,
        "failures": failures,
        "payloads": payloads,
    }


def defaults_file_key(*, resolution: str | None, horizon_label: str | None) -> str:
    """Bucket key for the defaults file: horizon label wins over resolution."""
    if horizon_label:
        return f"horizon:{horizon_label}"
    return f"resolution:{resolution or 'any'}"


def write_robust_defaults_file(
    strategy_payloads: dict[str, dict[str, Any]],
    defaults_path: Path,
    *,
    key: str | None = None,
) -> dict[str, Any]:
    """Merge tune payloads into the JSON defaults file; returns the file content."""
    existing: dict[str, Any] = {}
    if defaults_path.exists():
        existing = json.loads(defaults_path.read_text(encoding="utf-8"))
    first = next(iter(strategy_payloads.values()), None)
    bucket = key or defaults_file_key(
        resolution=(first or {}).get("resolution"),
        horizon_label=(first or {}).get("horizon_label"),
    )
    bucket_entry = dict(existing.get(bucket) or {})
    for strategy_id, payload in strategy_payloads.items():
        bucket_entry[strategy_id] = {
            "robust_params": dict(payload["robust_params"]),
            "best_params": dict(payload["best_params"]) if payload.get("best_params") else None,
            "basis": {
                "assets": list(payload.get("assets") or []),
                "asset_count": payload.get("asset_count"),
                "rank_by": payload.get("rank_by"),
                "mean_metric": payload.get("robust_metrics", {}).get("mean_metric"),
                "eligible_assets": payload.get("robust_metrics", {}).get("eligible_assets"),
                "param_grid": payload.get("param_grid"),
            },
        }
    existing[bucket] = bucket_entry
    defaults_path.parent.mkdir(parents=True, exist_ok=True)
    defaults_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return existing
