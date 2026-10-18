from __future__ import annotations

from typing import Any

from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.algorithms.strategy_defaults import namespace_for_strategy_backtest
from traderbot.backtesting import run_backtest
from traderbot.backtesting.oos_metrics import bars_per_year_for_resolution, summarize_single_asset_run
from traderbot.backtesting.research_windows import derive_walk_forward_run_start
from traderbot.discovery.candidate import CandidateEvaluation, DiscoveryCandidate
from traderbot.discovery.regime import regime_label_for_bars
from traderbot.markets.execution_costs import ExecutionCostProfile
from traderbot.utils.bars import filter_bars_by_unix_range


def _split_train_eval(bars: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int | None]:
    run_start = derive_walk_forward_run_start(bars)
    if run_start is None:
        return bars, [], None
    train_bars = [bar for bar in bars if int(bar["timestamp"]) < run_start]
    eval_bars = [bar for bar in bars if int(bar["timestamp"]) >= run_start]
    return train_bars, eval_bars, run_start


def _walk_forward_stability(
    eval_bars: list[dict[str, Any]],
    *,
    strategy_id: str,
    cost: ExecutionCostProfile,
    cash: float,
    execution: str,
    folds: int = 4,
) -> float | None:
    if len(eval_bars) < folds * 5:
        return None
    fold_size = len(eval_bars) // folds
    positive = 0
    scored = 0
    for fold_index in range(folds):
        start = fold_index * fold_size
        end = start + fold_size if fold_index < folds - 1 else len(eval_bars)
        window = eval_bars[start:end]
        if len(window) < 5:
            continue
        namespace = namespace_for_strategy_backtest(strategy_id, default_strategy_namespace())
        kwargs = strategy_kwargs_from_namespace(strategy_id, namespace)
        algo = algorithm_for_id(strategy_id, **kwargs)
        result = run_backtest(
            algo,
            window,
            initial_cash=cash,
            fee_rate=cost.fee_rate,
            slippage_rate=cost.slippage_rate,
            execution=execution,
        )
        scored += 1
        if result.return_pct > 0:
            positive += 1
    if scored == 0:
        return None
    return positive / scored


def _run_backtest_metrics(
    bars: list[dict[str, Any]],
    *,
    strategy_id: str,
    resolution: str,
    cost: ExecutionCostProfile,
    cash: float,
    execution: str,
) -> dict[str, Any]:
    namespace = namespace_for_strategy_backtest(strategy_id, default_strategy_namespace())
    kwargs = strategy_kwargs_from_namespace(strategy_id, namespace)
    algo = algorithm_for_id(strategy_id, **kwargs)
    result = run_backtest(
        algo,
        bars,
        initial_cash=cash,
        fee_rate=cost.fee_rate,
        slippage_rate=cost.slippage_rate,
        execution=execution,
    )
    summary = summarize_single_asset_run(result, bars, resolution=resolution, algorithm=algo)
    summary["total_fees"] = round(result.total_fees, 4)
    return summary


def evaluate_discovery_candidate(
    candidate: DiscoveryCandidate,
    bars: list[dict[str, Any]],
    *,
    cost: ExecutionCostProfile,
    cash: float,
    execution: str,
    min_bars: int,
    min_oos_bars: int,
    liquidity_score: float | None,
) -> CandidateEvaluation:
    data_quality: dict[str, Any] = {
        "bar_count": len(bars),
        "insufficient_bars": len(bars) < min_bars,
    }
    regime_label = regime_label_for_bars(bars)
    train_bars, eval_bars, run_start = _split_train_eval(bars)
    data_quality["run_start_unix_seconds"] = run_start
    data_quality["oos_bar_count"] = len(eval_bars)
    data_quality["insufficient_oos_bars"] = len(eval_bars) < min_oos_bars

    metrics: dict[str, Any] = {
        "params_source": candidate.params_source,
        "regime_label": regime_label,
        "regime_balance_score": 1.0,
        "parameter_stability_score": 1.0,
    }
    if eval_bars:
        oos = _run_backtest_metrics(
            eval_bars,
            strategy_id=candidate.strategy_id,
            resolution=candidate.resolution,
            cost=cost,
            cash=cash,
            execution=execution,
        )
        metrics.update(oos)
        metrics["oos_return_pct"] = oos.get("return_pct")
    else:
        metrics["oos_return_pct"] = None

    stability = _walk_forward_stability(
        eval_bars,
        strategy_id=candidate.strategy_id,
        cost=cost,
        cash=cash,
        execution=execution,
    )
    if train_bars and eval_bars:
        in_sample = _run_backtest_metrics(
            train_bars,
            strategy_id=candidate.strategy_id,
            resolution=candidate.resolution,
            cost=cost,
            cash=cash,
            execution=execution,
        )
        metrics["in_sample_return_pct"] = in_sample.get("return_pct")
        is_ret = float(in_sample.get("return_pct") or 0)
        oos_ret = float(metrics.get("oos_return_pct") or 0)
        if is_ret > 0:
            metrics["parameter_stability_score"] = min(1.0, max(0.0, oos_ret / is_ret))
        else:
            metrics["parameter_stability_score"] = 0.5 if oos_ret >= 0 else 0.0

    metrics["estimated_transaction_costs"] = metrics.get("total_fees")
    metrics["sharpe_ratio"] = metrics.get("sharpe_ratio")
    if metrics.get("sharpe_ratio") is None and eval_bars:
        metrics["bars_per_year"] = bars_per_year_for_resolution(candidate.resolution)

    return CandidateEvaluation(
        candidate=candidate,
        regime_label=regime_label,
        metrics=metrics,
        walk_forward_stability=stability,
        liquidity_score=liquidity_score,
        data_quality=data_quality,
    )


def filter_bars_for_job(
    bars: list[dict[str, Any]],
    *,
    resolution: str,
    run_start_unix_seconds: int | None,
    run_end_unix_seconds: int | None,
) -> list[dict[str, Any]]:
    from traderbot.hyperliquid.market_data import hyperliquid_resolution
    from traderbot.utils.resolution import resolution_minutes

    api_resolution = hyperliquid_resolution(str(resolution))
    bar_minutes = resolution_minutes(api_resolution)
    return filter_bars_by_unix_range(
        bars,
        start_unix_seconds=run_start_unix_seconds,
        end_unix_seconds=run_end_unix_seconds,
        bar_minutes=bar_minutes,
    )
