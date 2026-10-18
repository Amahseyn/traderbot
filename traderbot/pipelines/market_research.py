from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from traderbot.algorithms.registry import backtest_strategy_ids
from traderbot.hyperliquid.market_data import HYPERLIQUID_RESOLUTIONS
from traderbot.markets.registry import (
    DEFAULT_JOBS_PATH,
    list_hyperliquid_markets,
    list_supported_markets,
    market_spec_from_symbol,
)
from traderbot.pipelines.base import PipelineResult
from traderbot.solutions.layout import SOLUTIONS_ROOT, prepare_solution
from traderbot.utils.trading_costs import DEFAULT_TRADE_FEE_RATE

LogFn = Callable[[str], None]
DEFAULT_RESEARCH_INTERVALS: tuple[str, ...] = ("1", "5", "15", "60")
DEFAULT_EXPORT_DAYS = 30
DEFAULT_OPTUNA_TRIALS = 80


def research_body_defaults(**overrides: Any) -> dict[str, Any]:
    """Shared Lab custom-research / sweep settings for export → Optuna → compare."""
    body: dict[str, Any] = {
        "compare_strategies": True,
        "compare_mode": "strategies",
        "optimize_before_compare": True,
        "apply_sweep_winner": True,
        "use_optimized_strategy_params": True,
        "optimize_method": "optuna",
        "optimize_n_trials": DEFAULT_OPTUNA_TRIALS,
        "optimize_selection_mode": "validation",
        "full_grid": True,
        "visualize": True,
        "execution": "close",
        "fee": DEFAULT_TRADE_FEE_RATE,
        "cash": 10_000.0,
        "export_days": DEFAULT_EXPORT_DAYS,
        "out": "data",
        "crypto_layout": True,
    }
    body.update(overrides)
    return body


def build_export_jobs(
    market_symbols: list[str],
    *,
    intervals: list[str],
    export_days: int,
    exchange: str = "hyperliquid",
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for symbol in market_symbols:
        spec = market_spec_from_symbol(symbol)
        for interval in intervals:
            jobs.append(
                {
                    "symbol": spec.symbol,
                    "src": spec.src,
                    "dst": spec.dst,
                    "exchange": exchange,
                    "interval": str(interval),
                    "days": int(export_days),
                }
            )
    return jobs


def resolve_market_symbols(
    *,
    market_symbol: str | None = None,
    jobs_file: Path | None = None,
    exchange: str = "hyperliquid",
    top_markets: int | None = None,
    market_symbols: list[str] | None = None,
) -> list[str]:
    if market_symbols:
        return [market_spec_from_symbol(str(item)).symbol for item in market_symbols]
    if market_symbol:
        return [market_spec_from_symbol(market_symbol).symbol]
    if exchange == "hyperliquid":
        markets = list_hyperliquid_markets()
    else:
        markets = list_supported_markets(jobs_file or DEFAULT_JOBS_PATH)
    symbols = [market.symbol for market in markets]
    if top_markets is not None:
        if top_markets < 1:
            raise ValueError("top_markets must be at least 1")
        symbols = symbols[:top_markets]
    if not symbols:
        raise ValueError("no markets resolved for research pipeline")
    return symbols


def build_single_market_research_body(
    *,
    market_symbol: str,
    intervals: list[str] | None = None,
    export_days: int = DEFAULT_EXPORT_DAYS,
    exchange: str = "hyperliquid",
    optimize_n_trials: int = DEFAULT_OPTUNA_TRIALS,
    strategy_ids: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    interval_list = list(intervals or DEFAULT_RESEARCH_INTERVALS)
    symbol = market_spec_from_symbol(market_symbol).symbol
    body = research_body_defaults(
        export_days=export_days,
        optimize_n_trials=optimize_n_trials,
        exchange=exchange,
        **extra,
    )
    body["export_jobs"] = build_export_jobs(
        [symbol],
        intervals=interval_list,
        export_days=export_days,
        exchange=exchange,
    )
    if strategy_ids:
        body["strategy_ids"] = list(strategy_ids)
    return body


def build_full_universe_research_body(
    *,
    intervals: list[str] | None = None,
    export_days: int = DEFAULT_EXPORT_DAYS,
    exchange: str = "hyperliquid",
    jobs_file: Path | None = None,
    top_markets: int | None = 30,
    optimize_n_trials: int = DEFAULT_OPTUNA_TRIALS,
    strategy_ids: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    interval_list = list(intervals or DEFAULT_RESEARCH_INTERVALS)
    symbols = resolve_market_symbols(
        jobs_file=jobs_file,
        exchange=exchange,
        top_markets=top_markets,
    )
    body = research_body_defaults(
        export_days=export_days,
        optimize_n_trials=optimize_n_trials,
        exchange=exchange,
        **extra,
    )
    body["export_jobs"] = build_export_jobs(
        symbols,
        intervals=interval_list,
        export_days=export_days,
        exchange=exchange,
    )
    body["export_market_symbols"] = symbols
    body["export_intervals"] = interval_list
    body["max_export_combos"] = max(len(symbols) * len(interval_list), 1)
    if strategy_ids:
        body["strategy_ids"] = list(strategy_ids)
    else:
        body["strategy_ids"] = list(backtest_strategy_ids())
    return body


def run_market_research_body(body: dict[str, Any], *, log: LogFn | None = None) -> dict[str, Any]:
    from lab.custom_research import run_custom_research

    def _default_log(message: str, **_kwargs: Any) -> None:
        print(message, flush=True)

    logger = log or _default_log
    return run_custom_research(body, log=logger)


def pipeline_single_market_research(
    *,
    market_symbol: str = "BTCUSDT",
    intervals: str | list[str] | None = None,
    export_days: int = DEFAULT_EXPORT_DAYS,
    exchange: str = "hyperliquid",
    optimize_n_trials: int = DEFAULT_OPTUNA_TRIALS,
    strategy_ids: list[str] | None = None,
    solutions_root: Path = SOLUTIONS_ROOT,
    solution_root: Path | None = None,
    log: LogFn | None = None,
) -> PipelineResult:
    """Export one perp/spot market → Optuna per strategy × interval → strategy compare."""
    interval_list = _parse_intervals(intervals)
    layout = prepare_solution(
        "single-market-research",
        solutions_root=solutions_root,
        solution_root=solution_root,
        title="Single-market research",
        description=f"{market_symbol} export, Optuna optimize, strategy compare.",
    )
    result = PipelineResult(pipeline_id="single-market-research")
    body = build_single_market_research_body(
        market_symbol=market_symbol,
        intervals=interval_list,
        export_days=export_days,
        exchange=exchange,
        optimize_n_trials=optimize_n_trials,
        strategy_ids=strategy_ids,
    )
    summary = run_market_research_body(body, log=log)
    report_path = layout.reports / "single_market_research.json"
    report_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    result.add_step(
        "research",
        detail=f"{market_symbol} × {len(interval_list)} intervals",
        artifacts=[report_path],
    )
    result.outputs = {
        "solution_root": str(layout.root),
        "report": str(report_path),
        "market_symbol": market_spec_from_symbol(market_symbol).symbol,
        "intervals": interval_list,
        "summary": summary,
    }
    result.write_summary(layout.reports / "pipeline_summary.json")
    return result


def pipeline_full_universe_research(
    *,
    intervals: str | list[str] | None = None,
    export_days: int = DEFAULT_EXPORT_DAYS,
    exchange: str = "hyperliquid",
    jobs_file: Path | None = None,
    top_markets: int | None = 30,
    optimize_n_trials: int = DEFAULT_OPTUNA_TRIALS,
    strategy_ids: list[str] | None = None,
    solutions_root: Path = SOLUTIONS_ROOT,
    solution_root: Path | None = None,
    log: LogFn | None = None,
) -> PipelineResult:
    """Export many markets → Optuna all strategies on each CSV → compare (batched export jobs)."""
    interval_list = _parse_intervals(intervals)
    layout = prepare_solution(
        "full-universe-research",
        solutions_root=solutions_root,
        solution_root=solution_root,
        title="Full-universe research",
        description="Multi-market export, Optuna optimize every strategy, compare.",
    )
    result = PipelineResult(pipeline_id="full-universe-research")
    body = build_full_universe_research_body(
        intervals=interval_list,
        export_days=export_days,
        exchange=exchange,
        jobs_file=jobs_file,
        top_markets=top_markets,
        optimize_n_trials=optimize_n_trials,
        strategy_ids=strategy_ids,
    )
    job_count = len(body.get("export_jobs") or [])
    strategy_count = len(body.get("strategy_ids") or [])
    if log:
        log(
            f"full-universe: {job_count} export jobs, {strategy_count} strategies, "
            f"optuna trials={optimize_n_trials}",
        )
    summary = run_market_research_body(body, log=log)
    report_path = layout.reports / "full_universe_research.json"
    report_path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    result.add_step(
        "research",
        detail=f"{job_count} exports, {strategy_count} strategies",
        artifacts=[report_path],
    )
    result.outputs = {
        "solution_root": str(layout.root),
        "report": str(report_path),
        "export_job_count": job_count,
        "strategy_count": strategy_count,
        "summary": summary,
    }
    result.write_summary(layout.reports / "pipeline_summary.json")
    return result


def _parse_intervals(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return list(DEFAULT_RESEARCH_INTERVALS)
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",") if part.strip()]
    else:
        parts = [str(part).strip() for part in raw if str(part).strip()]
    if not parts:
        return list(DEFAULT_RESEARCH_INTERVALS)
    allowed = set(HYPERLIQUID_RESOLUTIONS)
    for part in parts:
        if part not in allowed:
            raise ValueError(f"unsupported interval {part!r}; allowed: {sorted(allowed)}")
    return parts
