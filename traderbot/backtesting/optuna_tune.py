from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Literal

from traderbot.algorithms.cli_args import merge_strategy_namespace
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.backtesting import backtest_summary_dict, load_bars_csv, run_backtest
from traderbot.backtesting.metrics import buy_and_hold_return_pct, max_drawdown_pct, split_chronological
from traderbot.backtesting.sweep import SweepOptions, sweep_rank_key
from traderbot.backtesting.tune_search_space import resolve_tune_param_names, suggest_strategy_params
from traderbot.data.intrahour import enrich_bars_for_csv

logger = logging.getLogger(__name__)

DEFAULT_OPTUNA_TRIALS = 80
DEFAULT_OPTUNA_TOP_ROWS = 25


def _require_optuna() -> Any:
    try:
        import optuna
    except ImportError as exc:
        raise ImportError(
            "Optuna is required for optimize_method=optuna. "
            'Install with: pip install -e ".[ui]" or pip install optuna>=3.6'
        ) from exc
    return optuna


@dataclass(frozen=True, slots=True)
class OptunaTuneConfig:
    n_trials: int = DEFAULT_OPTUNA_TRIALS
    timeout_seconds: float | None = None
    search_params: tuple[str, ...] | None = None
    full_grid_hints: bool = True
    sampler: Literal["tpe", "random"] = "tpe"
    top_rows: int = DEFAULT_OPTUNA_TOP_ROWS


def _load_bars(options: SweepOptions, base: Any) -> tuple[list[dict[str, Any]], str, Any]:
    if options.bars is not None:
        bars = list(options.bars)
        if options.max_bars is not None and len(bars) > options.max_bars:
            bars = bars[-options.max_bars :]
        csv_label = str(options.csv_path or options.strategy_id)
        return bars, csv_label, base
    if options.csv_path is None:
        raise ValueError("optuna tune requires csv_path or preloaded bars")
    csv_path = options.csv_path
    csv_label = str(csv_path)
    bars = enrich_bars_for_csv(load_bars_csv(csv_path), csv_path, base)
    if not bars:
        raise ValueError(f"No bars in CSV: {csv_path}")
    if options.max_bars is not None and len(bars) > options.max_bars:
        bars = bars[-options.max_bars :]
    return bars, csv_label, base


def _evaluate_params(
    *,
    strategy_id: str,
    params: dict[str, Any],
    base: Any,
    train_bars: list[dict[str, Any]],
    validation_bars: list[dict[str, Any]] | None,
    options: SweepOptions,
) -> dict[str, Any]:
    namespace = merge_strategy_namespace(base)
    for key, value in params.items():
        setattr(namespace, key, value)
    train_algo = algorithm_for_id(
        strategy_id,
        **strategy_kwargs_from_namespace(strategy_id, namespace),
    )
    train_result = run_backtest(
        train_algo,
        train_bars,
        initial_cash=options.cash,
        fee_rate=options.fee,
        slippage_rate=options.slippage,
        execution=options.execution,
    )
    train_summary = backtest_summary_dict(
        train_algo,
        train_result,
        bars=len(train_bars),
        extra={"strategy_id": strategy_id},
    )
    validation_summary: dict[str, Any] | None = None
    validation_return = float(train_summary["return_pct"])
    validation_trades = int(train_summary["trades"])
    if validation_bars is not None:
        validation_algo = algorithm_for_id(
            strategy_id,
            **strategy_kwargs_from_namespace(strategy_id, namespace),
        )
        validation_result = run_backtest(
            validation_algo,
            validation_bars,
            initial_cash=options.cash,
            fee_rate=options.fee,
            slippage_rate=options.slippage,
            execution=options.execution,
        )
        validation_summary = backtest_summary_dict(
            validation_algo,
            validation_result,
            bars=len(validation_bars),
            extra={"strategy_id": strategy_id},
        )
        validation_return = float(validation_summary["return_pct"])
        validation_trades = int(validation_summary["trades"])
    eligible = (
        int(train_summary["trades"]) >= options.min_trades
        and validation_trades >= options.min_trades
    )
    return {
        "params": dict(params),
        "train": train_summary,
        "validation": validation_summary or train_summary,
        "eligible": eligible,
        "validation_return_pct": validation_return,
        "validation_trades": validation_trades,
    }


def _selection_key(row: dict[str, Any]) -> tuple[int, float, float]:
    return (
        1 if row.get("eligible") else 0,
        float(row.get("validation_return_pct") or float("-inf")),
        float(row["train"]["return_pct"]),
    )


def run_strategy_optuna_tune(
    options: SweepOptions,
    base_namespace: Any | None,
    *,
    tune_config: OptunaTuneConfig,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
    use_validation_split: bool = True,
) -> dict[str, Any]:
    """Bayesian search over many strategy params; objective = validation return (default)."""
    optuna = _require_optuna()
    trial_pruned = optuna.exceptions.TrialPruned
    base = merge_strategy_namespace(base_namespace)
    bars, csv_label, base = _load_bars(options, base)
    param_names = resolve_tune_param_names(
        options.strategy_id,
        search_params=list(tune_config.search_params) if tune_config.search_params else None,
    )
    if use_validation_split:
        train_bars, validation_bars, test_bars = split_chronological(
            bars,
            train_fraction=train_fraction,
            validation_fraction=validation_fraction,
        )
    else:
        holdout = options.holdout_tail_bars
        if holdout is not None and len(bars) > holdout:
            train_bars = bars[:-holdout]
            validation_bars = None
            test_bars = bars[-holdout:]
        else:
            train_bars = bars
            validation_bars = None
            test_bars = bars

    trial_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    def objective(trial: Any) -> float:
        try:
            params = suggest_strategy_params(
                trial,
                options.strategy_id,
                param_names,
                full_grid_hints=tune_config.full_grid_hints,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "TrialPruned":
                raise
            skipped.append({"trial": trial.number, "error": str(exc)})
            raise trial_pruned(str(exc)) from exc
        try:
            row = _evaluate_params(
                strategy_id=options.strategy_id,
                params=params,
                base=base,
                train_bars=train_bars,
                validation_bars=validation_bars if use_validation_split else None,
                options=options,
            )
        except ValueError as exc:
            skipped.append({"params": params, "error": str(exc)})
            raise trial_pruned(str(exc)) from exc
        trial.set_user_attr("params", params)
        trial.set_user_attr("eligible", row["eligible"])
        trial_rows.append(row)
        return float(row["validation_return_pct"])

    sampler: Any
    if tune_config.sampler == "random":
        sampler = optuna.samplers.RandomSampler()
    else:
        sampler = optuna.samplers.TPESampler(multivariate=True)

    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(
        objective,
        n_trials=max(1, tune_config.n_trials),
        timeout=tune_config.timeout_seconds,
        show_progress_bar=False,
        catch=(ValueError,),
    )
    if not trial_rows:
        reason = skipped[0]["error"] if skipped else "no completed trials"
        raise ValueError(f"optuna found no valid trials: {reason}")

    trial_rows.sort(key=_selection_key, reverse=True)
    winner = trial_rows[0]
    winner_params = dict(winner["params"])
    winner_namespace = merge_strategy_namespace(base)
    for key, value in winner_params.items():
        setattr(winner_namespace, key, value)
    test_algo = algorithm_for_id(
        options.strategy_id,
        **strategy_kwargs_from_namespace(options.strategy_id, winner_namespace),
    )
    test_result = run_backtest(
        test_algo,
        test_bars if use_validation_split else bars,
        initial_cash=options.cash,
        fee_rate=options.fee,
        slippage_rate=options.slippage,
        execution=options.execution,
    )
    benchmark_return = buy_and_hold_return_pct(
        test_bars if use_validation_split else bars,
        initial_cash=options.cash,
        fee_rate=options.fee,
        slippage_rate=options.slippage,
        execution=options.execution,
    )
    rank_by = "validation_return_pct" if use_validation_split else "return_pct"

    return {
        "csv": csv_label,
        "strategy_id": options.strategy_id,
        "bars": len(bars),
        "splits": {
            "train": len(train_bars),
            "validation": len(validation_bars) if validation_bars is not None else 0,
            "test": len(test_bars) if use_validation_split else len(bars),
        },
        "fee": options.fee,
        "slippage": options.slippage,
        "execution": options.execution,
        "selection": rank_by,
        "combos_tried": len(study.trials),
        "skipped": skipped,
        "selected_params": winner_params,
        "candidates": trial_rows[: tune_config.top_rows],
        "test": {
            **backtest_summary_dict(
                test_algo,
                test_result,
                bars=len(test_bars if use_validation_split else bars),
                extra={"strategy_id": options.strategy_id},
            ),
            "max_drawdown_pct": round(max_drawdown_pct(list(test_result.equity_curve)), 6),
            "buy_and_hold_return_pct": round(benchmark_return, 6),
            "excess_return_vs_buy_hold_pct": round(
                test_result.return_pct - benchmark_return,
                6,
            ),
        },
        "optuna": {
            "n_trials": len(study.trials),
            "n_completed": len([trial for trial in study.trials if trial.state.name == "COMPLETE"]),
            "best_value": study.best_value if study.best_trial else None,
            "sampler": tune_config.sampler,
            "search_params": param_names,
        },
    }


def run_strategy_optuna_in_sample(
    options: SweepOptions,
    base_namespace: Any | None,
    *,
    tune_config: OptunaTuneConfig,
) -> dict[str, Any]:
    """Optuna on a single training window (optional holdout reported, not in objective)."""
    optuna = _require_optuna()
    trial_pruned = optuna.exceptions.TrialPruned
    base = merge_strategy_namespace(base_namespace)
    bars, csv_label, base = _load_bars(options, base)
    param_names = resolve_tune_param_names(
        options.strategy_id,
        search_params=list(tune_config.search_params) if tune_config.search_params else None,
    )
    holdout_bars = options.holdout_tail_bars
    train_bars = bars
    if holdout_bars is not None:
        if len(bars) <= holdout_bars:
            raise ValueError(f"holdout_tail_bars={holdout_bars} needs more bars (got {len(bars)})")
        train_bars = bars[:-holdout_bars]

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    def objective(trial: Any) -> float:
        try:
            params = suggest_strategy_params(
                trial,
                options.strategy_id,
                param_names,
                full_grid_hints=tune_config.full_grid_hints,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "TrialPruned":
                raise
            raise trial_pruned(str(exc)) from exc
        namespace = merge_strategy_namespace(base)
        for key, value in params.items():
            setattr(namespace, key, value)
        try:
            algo = algorithm_for_id(
                options.strategy_id,
                **strategy_kwargs_from_namespace(options.strategy_id, namespace),
            )
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
            raise trial_pruned(str(exc)) from exc
        summary = backtest_summary_dict(
            algo,
            result,
            bars=len(train_bars),
            extra={"strategy_id": options.strategy_id},
        )
        summary["params"] = dict(params)
        summary["eligible"] = summary["trades"] >= options.min_trades
        rows.append(summary)
        if not summary["eligible"]:
            return float("-inf")
        return float(summary["return_pct"])

    sampler = (
        optuna.samplers.RandomSampler()
        if tune_config.sampler == "random"
        else optuna.samplers.TPESampler(multivariate=True)
    )
    study = optuna.create_study(direction="maximize", sampler=sampler)
    study.optimize(
        objective,
        n_trials=max(1, tune_config.n_trials),
        timeout=tune_config.timeout_seconds,
        show_progress_bar=False,
        catch=(ValueError,),
    )
    if not rows:
        raise ValueError("optuna in_sample found no valid trials")
    rows.sort(key=lambda row: sweep_rank_key(row, rank_by="return_pct"), reverse=True)
    best = rows[0]
    best_params = dict(best.get("params") or {})
    payload: dict[str, Any] = {
        "csv": csv_label,
        "strategy_id": options.strategy_id,
        "bars": len(bars),
        "cash": options.cash,
        "fee": options.fee,
        "slippage": options.slippage,
        "execution": options.execution,
        "holdout_tail_bars": holdout_bars,
        "min_trades": options.min_trades,
        "rank_by": "return_pct",
        "selection_mode": "in_sample",
        "param_grid": {name: ["optuna"] for name in param_names},
        "combinations": len(study.trials),
        "skipped": skipped,
        "best_params": best_params,
        "best": best,
        "rows": rows[: tune_config.top_rows],
        "optimizer_method": "optuna",
        "optuna": {
            "n_trials": len(study.trials),
            "best_value": study.best_value if study.best_trial else None,
            "sampler": tune_config.sampler,
            "search_params": param_names,
        },
    }
    return payload
