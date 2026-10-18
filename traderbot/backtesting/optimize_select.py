from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from traderbot.backtesting.sweep import SweepOptions, run_strategy_sweep
from traderbot.backtesting.validation import ValidationOptions, run_strategy_validation

logger = logging.getLogger(__name__)

OptimizeSelectionMode = Literal["validation", "in_sample"]
OptimizeMethod = Literal["grid", "optuna"]

DEFAULT_OPTIMIZE_SELECTION_MODE: OptimizeSelectionMode = "validation"
DEFAULT_OPTIMIZE_METHOD: OptimizeMethod = "grid"
MIN_BARS_FOR_VALIDATION_SPLIT = 30
DEFAULT_TRAIN_FRACTION = 0.6
DEFAULT_VALIDATION_FRACTION = 0.2


def normalize_optimize_selection_mode(raw: Any) -> OptimizeSelectionMode:
    if raw in (None, ""):
        return DEFAULT_OPTIMIZE_SELECTION_MODE
    mode = str(raw).strip().lower()
    if mode in ("validation", "in_sample"):
        return mode  # type: ignore[return-value]
    raise ValueError(f"optimize_selection_mode must be validation or in_sample (got {raw!r})")


def normalize_optimize_method(raw: Any) -> OptimizeMethod:
    if raw in (None, ""):
        return DEFAULT_OPTIMIZE_METHOD
    method = str(raw).strip().lower()
    if method in ("grid", "optuna", "bayesian"):
        return "optuna" if method in ("optuna", "bayesian") else "grid"
    raise ValueError(f"optimize_method must be grid or optuna (got {raw!r})")


def holdout_tail_for_bar_count(bar_count: int, *, holdout_fraction: float = 0.2) -> int | None:
    if bar_count <= 10:
        return None
    return max(1, int(bar_count * holdout_fraction))


@dataclass(frozen=True, slots=True)
class OptimizeSelectConfig:
    selection_mode: OptimizeSelectionMode = DEFAULT_OPTIMIZE_SELECTION_MODE
    train_fraction: float = DEFAULT_TRAIN_FRACTION
    validation_fraction: float = DEFAULT_VALIDATION_FRACTION
    holdout_fraction: float = 0.2
    optimizer_method: OptimizeMethod = DEFAULT_OPTIMIZE_METHOD
    n_trials: int = 80
    timeout_seconds: float | None = None
    search_params: tuple[str, ...] | None = None
    optuna_sampler: Literal["tpe", "random"] = "tpe"
    full_grid_hints: bool = True


def _validation_payload_to_sweep(
    validation_payload: dict[str, Any],
    *,
    options: SweepOptions,
    bar_minutes: int | None,
) -> dict[str, Any]:
    winner_params = dict(validation_payload.get("selected_params") or {})
    candidates = list(validation_payload.get("candidates") or [])
    winner = candidates[0] if candidates else None
    rows: list[dict[str, Any]] = []
    for row in candidates:
        train_summary = dict(row.get("train") or {})
        validation_summary = dict(row.get("validation") or {})
        params = dict(row.get("params") or {})
        merged = {
            **train_summary,
            "params": params,
            "validation_return_pct": validation_summary.get("return_pct"),
            "validation_trades": validation_summary.get("trades"),
            "eligible": bool(row.get("eligible")),
        }
        rows.append(merged)

    best_row: dict[str, Any] | None = None
    if winner:
        train_summary = dict(winner.get("train") or {})
        validation_summary = dict(winner.get("validation") or {})
        best_row = {
            **train_summary,
            "params": dict(winner.get("params") or {}),
            "validation_return_pct": validation_summary.get("return_pct"),
            "validation_trades": validation_summary.get("trades"),
            "eligible": bool(winner.get("eligible")),
        }

    csv_label = str(validation_payload.get("csv", ""))
    if options.csv_path is not None:
        csv_label = str(options.csv_path)

    from traderbot.backtesting.bar_windows import (
        fit_window_utc_from_bars,
        infer_bar_minutes,
        sample_window_utc_from_bars,
    )

    bars_count = int(validation_payload.get("bars") or 0)
    if options.bars is not None:
        bar_list = list(options.bars)
        if options.max_bars is not None and len(bar_list) > options.max_bars:
            bar_list = bar_list[-options.max_bars :]
    elif options.csv_path is not None:
        from traderbot.algorithms.cli_args import default_strategy_namespace
        from traderbot.backtesting import load_bars_csv
        from traderbot.data.intrahour import enrich_bars_for_csv

        base = default_strategy_namespace()
        bar_list = enrich_bars_for_csv(load_bars_csv(Path(options.csv_path)), options.csv_path, base)
        if options.max_bars is not None and len(bar_list) > options.max_bars:
            bar_list = bar_list[-options.max_bars :]
    else:
        bar_list = []

    if bar_minutes is None and bar_list:
        bar_minutes = infer_bar_minutes(bar_list)
    bar_minutes = bar_minutes or 60

    optimize_start_utc, optimize_end_utc = (None, None)
    sample_start_utc, sample_end_utc = (None, None)
    if bar_list:
        optimize_start_utc, optimize_end_utc = fit_window_utc_from_bars(
            bar_list,
            bar_minutes=bar_minutes,
            holdout_tail_bars=None,
        )
        sample_start_utc, sample_end_utc = sample_window_utc_from_bars(bar_list, bar_minutes=bar_minutes)

    return {
        "csv": csv_label,
        "strategy_id": validation_payload.get("strategy_id"),
        "bars": bars_count,
        "bar_minutes": bar_minutes,
        "optimize_start_utc": optimize_start_utc,
        "optimize_end_utc": optimize_end_utc,
        "sample_start_utc": sample_start_utc,
        "sample_end_utc": sample_end_utc,
        "holdout_start_utc": None,
        "holdout_end_utc": None,
        "cash": options.cash,
        "fee": options.fee,
        "slippage": options.slippage,
        "execution": options.execution,
        "holdout_tail_bars": None,
        "min_trades": options.min_trades,
        "rank_by": "validation_return_pct" if options.rank_by == "return_pct" else "validation_edge",
        "selection_mode": "validation",
        "selection_mode_applied": "validation",
        "train_fraction": validation_payload.get("train_fraction"),
        "validation_fraction": validation_payload.get("validation_fraction"),
        "param_grid": {name: list(values) for name, values in options.param_grid.items()},
        "combinations": validation_payload.get("combos_tried"),
        "skipped": validation_payload.get("skipped"),
        "best_params": winner_params or None,
        "best": best_row,
        "rows": rows,
        "splits": validation_payload.get("splits"),
        "test": validation_payload.get("test"),
        "validation_selection": validation_payload.get("selection"),
    }


def _trimmed_bars_for_options(options: SweepOptions) -> list[dict[str, Any]] | None:
    if options.bars is None:
        return None
    bars = list(options.bars)
    if options.max_bars is not None and len(bars) > options.max_bars:
        bars = bars[-options.max_bars :]
    return bars


def _bar_count_for_options(options: SweepOptions) -> int:
    if options.bars is not None:
        return len(_trimmed_bars_for_options(options) or [])
    if options.csv_path is None:
        return 0
    from traderbot.backtesting import load_bars_csv

    count = len(load_bars_csv(Path(options.csv_path)))
    if options.max_bars is not None:
        count = min(count, options.max_bars)
    return count


def run_strategy_optimize(
    options: SweepOptions,
    base_namespace: Any | None = None,
    *,
    config: OptimizeSelectConfig | None = None,
) -> dict[str, Any]:
    """Grid or Optuna optimize with validation-based selection (default) or in-sample."""
    cfg = config or OptimizeSelectConfig()
    mode = cfg.selection_mode
    bar_count = _bar_count_for_options(options)

    if cfg.optimizer_method == "optuna":
        from traderbot.backtesting.optuna_tune import OptunaTuneConfig, run_strategy_optuna_in_sample, run_strategy_optuna_tune

        tune_config = OptunaTuneConfig(
            n_trials=cfg.n_trials,
            timeout_seconds=cfg.timeout_seconds,
            search_params=cfg.search_params,
            full_grid_hints=cfg.full_grid_hints,
            sampler=cfg.optuna_sampler,
        )
        use_validation = mode == "validation" and bar_count >= MIN_BARS_FOR_VALIDATION_SPLIT
        if mode == "validation" and not use_validation:
            logger.info(
                "optimize optuna: %s bars < %s — falling back to in_sample",
                bar_count,
                MIN_BARS_FOR_VALIDATION_SPLIT,
            )
        if use_validation:
            validation_payload = run_strategy_optuna_tune(
                options,
                base_namespace,
                tune_config=tune_config,
                train_fraction=cfg.train_fraction,
                validation_fraction=cfg.validation_fraction,
                use_validation_split=True,
            )
            optuna_meta = validation_payload.pop("optuna", None)
            validation_payload["train_fraction"] = cfg.train_fraction
            validation_payload["validation_fraction"] = cfg.validation_fraction
            payload = _validation_payload_to_sweep(validation_payload, options=options, bar_minutes=None)
            payload["optimizer_method"] = "optuna"
            if optuna_meta:
                payload["optuna"] = optuna_meta
            payload["selection_mode"] = "validation"
            payload["selection_mode_applied"] = "validation"
            return payload
        payload = run_strategy_optuna_in_sample(options, base_namespace, tune_config=tune_config)
        payload["selection_mode_applied"] = (
            "in_sample_fallback" if mode == "validation" else "in_sample"
        )
        return payload

    use_validation = mode == "validation" and bar_count >= MIN_BARS_FOR_VALIDATION_SPLIT
    if mode == "validation" and not use_validation:
        logger.info(
            "optimize: %s bars < %s — falling back to in_sample holdout",
            bar_count,
            MIN_BARS_FOR_VALIDATION_SPLIT,
        )

    if use_validation:
        trimmed_bars = _trimmed_bars_for_options(options)
        validation_payload = run_strategy_validation(
            ValidationOptions(
                csv_path=options.csv_path if trimmed_bars is None else None,
                strategy_id=options.strategy_id,
                param_grid=options.param_grid,
                bars=trimmed_bars if trimmed_bars is not None else options.bars,
                cash=options.cash,
                fee=options.fee,
                slippage=options.slippage,
                execution=options.execution,
                train_fraction=cfg.train_fraction,
                validation_fraction=cfg.validation_fraction,
                min_trades=options.min_trades,
                max_combos=options.max_combos,
                rank_by="return_pct" if options.rank_by == "return_pct" else "edge",
            ),
            base_namespace,
        )
        validation_payload["train_fraction"] = cfg.train_fraction
        validation_payload["validation_fraction"] = cfg.validation_fraction
        payload = _validation_payload_to_sweep(validation_payload, options=options, bar_minutes=None)
        return payload

    trimmed_bars = _trimmed_bars_for_options(options)
    sweep_options = SweepOptions(
        strategy_id=options.strategy_id,
        param_grid=options.param_grid,
        csv_path=options.csv_path,
        bars=trimmed_bars if trimmed_bars is not None else options.bars,
        cash=options.cash,
        fee=options.fee,
        slippage=options.slippage,
        execution=options.execution,
        holdout_tail_bars=options.holdout_tail_bars,
        min_trades=options.min_trades,
        max_combos=options.max_combos,
        max_bars=options.max_bars,
    )
    if sweep_options.holdout_tail_bars is None and bar_count > 10:
        sweep_options = SweepOptions(
            strategy_id=sweep_options.strategy_id,
            param_grid=sweep_options.param_grid,
            csv_path=sweep_options.csv_path,
            bars=sweep_options.bars,
            cash=sweep_options.cash,
            fee=sweep_options.fee,
            slippage=sweep_options.slippage,
            execution=sweep_options.execution,
            holdout_tail_bars=holdout_tail_for_bar_count(bar_count, holdout_fraction=cfg.holdout_fraction),
            min_trades=sweep_options.min_trades,
            max_combos=sweep_options.max_combos,
            max_bars=sweep_options.max_bars,
        )
    payload = run_strategy_sweep(sweep_options, base_namespace)
    payload["selection_mode"] = "in_sample"
    payload["selection_mode_applied"] = (
        "in_sample_fallback" if mode == "validation" else "in_sample"
    )
    return payload


def optimize_config_from_body(body: dict[str, Any]) -> OptimizeSelectConfig:
    train_fraction = float(body.get("train_fraction") or DEFAULT_TRAIN_FRACTION)
    validation_fraction = float(body.get("validation_fraction") or DEFAULT_VALIDATION_FRACTION)
    if train_fraction <= 0 or validation_fraction <= 0 or train_fraction + validation_fraction >= 1:
        raise ValueError("train_fraction and validation_fraction must be positive and sum to < 1")
    n_trials_raw = body.get("optimize_n_trials", body.get("n_trials"))
    n_trials = int(n_trials_raw) if n_trials_raw not in (None, "") else 80
    if n_trials < 1:
        raise ValueError("optimize_n_trials must be at least 1")
    timeout_raw = body.get("optimize_timeout_seconds", body.get("timeout_seconds"))
    timeout_seconds = float(timeout_raw) if timeout_raw not in (None, "") else None
    search_raw = body.get("optimize_search_params", body.get("search_params"))
    search_params: tuple[str, ...] | None = None
    if isinstance(search_raw, list) and search_raw:
        search_params = tuple(str(name).strip() for name in search_raw if str(name).strip())
    sampler_raw = str(body.get("optuna_sampler") or "tpe").strip().lower()
    optuna_sampler: Literal["tpe", "random"] = "random" if sampler_raw == "random" else "tpe"
    return OptimizeSelectConfig(
        selection_mode=normalize_optimize_selection_mode(body.get("optimize_selection_mode")),
        train_fraction=train_fraction,
        validation_fraction=validation_fraction,
        optimizer_method=normalize_optimize_method(
            body.get("optimize_method", body.get("optimizer_method"))
        ),
        n_trials=n_trials,
        timeout_seconds=timeout_seconds,
        search_params=search_params,
        optuna_sampler=optuna_sampler,
        full_grid_hints=bool(body.get("full_grid", True)),
    )
