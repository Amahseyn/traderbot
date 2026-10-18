from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from traderbot.algorithms.registry import backtest_strategy_ids
from traderbot.algorithms.strategy_exchanges import strategy_supported_on
from traderbot.backtesting.eval_data import fetch_history_bars
from traderbot.discovery.candidate import DiscoveryCandidate
from traderbot.discovery.evaluate import evaluate_discovery_candidate, filter_bars_for_job
from traderbot.discovery.report import build_discovery_report
from traderbot.discovery.score import (
    DEFAULT_SCORING_CONFIG,
    ScoringConfig,
    score_evaluation,
    scoring_config_from_dict,
    scoring_config_to_dict,
)
from traderbot.discovery.market_metrics import (
    compute_market_bar_metrics,
    market_metrics_to_dict,
    score_market_opportunity,
    volume_percentiles,
)
from traderbot.discovery.universe import UniverseFilters, discover_hyperliquid_perp_universe
from traderbot.markets.execution_costs import FeeRole, execution_cost_profile
from traderbot.markets.exchange import normalize_live_exchange
from traderbot.utils.trading_costs import DEFAULT_BACKTEST_EXECUTION

DEFAULT_RESOLUTIONS = ("5", "15", "60", "240", "D")


@dataclass
class DiscoveryConfig:
    exchange: str = "hyperliquid"
    symbols: list[str] = field(default_factory=list)
    resolutions: list[str] = field(default_factory=lambda: list(DEFAULT_RESOLUTIONS))
    strategy_ids: list[str] = field(default_factory=list)
    months: int = 6
    use_cache: bool = True
    cash: float = 10_000.0
    fee_role: str = "taker"
    execution: str = DEFAULT_BACKTEST_EXECUTION
    min_trades: int = 5
    max_drawdown_pct: float = -40.0
    min_bars: int = 120
    min_oos_bars: int = 30
    min_mean_volume_quote: float = 0.0
    max_symbols: int = 24
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    run_start_unix_seconds: int | None = None
    run_end_unix_seconds: int | None = None
    out_dir: Path | None = None
    evaluate_strategies: bool = True


def discovery_config_from_body(body: dict[str, Any]) -> DiscoveryConfig:
    exchange = normalize_live_exchange(str(body.get("exchange") or "hyperliquid"))
    resolutions_raw = body.get("resolutions")
    if isinstance(resolutions_raw, list) and resolutions_raw:
        resolutions = [str(item).strip() for item in resolutions_raw if str(item).strip()]
    elif isinstance(resolutions_raw, str) and resolutions_raw.strip():
        resolutions = [part.strip() for part in resolutions_raw.split(",") if part.strip()]
    else:
        resolutions = list(DEFAULT_RESOLUTIONS)
    symbols_raw = body.get("symbols")
    symbols: list[str] = []
    if isinstance(symbols_raw, list):
        symbols = [str(item).strip().lower() for item in symbols_raw if str(item).strip()]
    strategy_raw = body.get("strategy_ids")
    strategy_ids: list[str] = []
    if isinstance(strategy_raw, list) and strategy_raw:
        strategy_ids = [str(item).strip() for item in strategy_raw if str(item).strip()]
    scoring = scoring_config_from_dict(body.get("scoring") if isinstance(body.get("scoring"), dict) else None)
    scoring.min_trades = int(body.get("min_trades") or scoring.min_trades)
    scoring.max_drawdown_pct = float(body.get("max_drawdown_pct") if body.get("max_drawdown_pct") is not None else scoring.max_drawdown_pct)
    out = body.get("out")
    return DiscoveryConfig(
        exchange=exchange,
        symbols=symbols,
        resolutions=resolutions,
        strategy_ids=strategy_ids,
        months=int(body.get("months") or 6),
        use_cache=bool(body.get("use_cache", True)),
        cash=float(body.get("cash") or 10_000.0),
        fee_role=str(body.get("fee_role") or "taker"),
        execution=str(body.get("execution") or DEFAULT_BACKTEST_EXECUTION),
        min_trades=int(body.get("min_trades") or 5),
        max_drawdown_pct=float(body.get("max_drawdown_pct") if body.get("max_drawdown_pct") is not None else -40.0),
        min_bars=int(body.get("min_bars") or 120),
        min_oos_bars=int(body.get("min_oos_bars") or 30),
        min_mean_volume_quote=float(body.get("min_mean_volume_quote") or 0.0),
        max_symbols=int(body.get("max_symbols") or 24),
        scoring=scoring,
        run_start_unix_seconds=int(body["run_start_unix_seconds"]) if body.get("run_start_unix_seconds") not in (None, "") else None,
        run_end_unix_seconds=int(body["run_end_unix_seconds"]) if body.get("run_end_unix_seconds") not in (None, "") else None,
        out_dir=Path(str(out)) if out else None,
        evaluate_strategies=body.get("evaluate_strategies", True) is not False,
    )


def _liquidity_score_for_entry(
    entry: Any,
    *,
    min_mean_volume_quote: float,
) -> float | None:
    if entry.mean_volume_quote_24h is None:
        return None
    if min_mean_volume_quote > 0:
        return min(1.0, entry.mean_volume_quote_24h / min_mean_volume_quote)
    return min(1.0, entry.mean_volume_quote_24h / 1_000_000.0)


def _merge_market_metrics_into_evaluation(
    evaluation: Any,
    bar_metrics: Any,
    *,
    liquidity_score: float | None,
    volume_percentile: float | None,
    set_composite_score: bool,
) -> None:
    evaluation.metrics = {
        **market_metrics_to_dict(bar_metrics),
        "liquidity_score": liquidity_score,
        "volume_percentile": volume_percentile,
    }
    if evaluation.rejection_reason or not set_composite_score:
        return
    composite, components = score_market_opportunity(
        bar_metrics,
        volume_percentile=volume_percentile,
    )
    evaluation.composite_score = composite
    evaluation.component_scores = components


def _run_market_liquidity_scan(
    config: DiscoveryConfig,
    *,
    tradable: list[Any],
    venue: str,
    cost: Any,
    log: Callable[[str], None],
    fetch_bars: Callable[..., list[dict[str, Any]]],
) -> dict[str, Any]:
    from traderbot.discovery.candidate import CandidateEvaluation, DiscoveryCandidate
    from traderbot.discovery.regime import regime_label_for_bars

    evaluations: list[CandidateEvaluation] = []
    pending_scores: list[tuple[CandidateEvaluation, Any, float | None, list[dict[str, Any]]]] = []

    for entry in tradable:
        liquidity_score = _liquidity_score_for_entry(
            entry,
            min_mean_volume_quote=config.min_mean_volume_quote,
        )
        for resolution in config.resolutions:
            log(f"discovery: market scan {entry.symbol_key} {resolution}")
            bars = fetch_bars(
                exchange=venue,
                symbol_key=entry.symbol_key,
                resolution=resolution,
                months=config.months,
                use_cache=config.use_cache,
            )
            bars = filter_bars_for_job(
                bars,
                resolution=resolution,
                run_start_unix_seconds=config.run_start_unix_seconds,
                run_end_unix_seconds=config.run_end_unix_seconds,
            )
            bar_metrics = compute_market_bar_metrics(bars)
            data_quality = {
                "bar_count": len(bars),
                "insufficient_bars": len(bars) < config.min_bars,
                "mean_volume_quote_24h": entry.mean_volume_quote_24h,
            }
            rejection_reason = None
            if len(bars) < config.min_bars:
                rejection_reason = "insufficient_bars"
            candidate = DiscoveryCandidate(
                exchange=venue,
                symbol_key=entry.symbol_key,
                market_symbol=entry.market_symbol,
                resolution=resolution,
                strategy_id="",
                params_source="market_scan",
            )
            evaluation = CandidateEvaluation(
                candidate=candidate,
                regime_label=regime_label_for_bars(bars) if bars else "uncertain",
                metrics=market_metrics_to_dict(bar_metrics),
                walk_forward_stability=None,
                liquidity_score=liquidity_score,
                data_quality=data_quality,
                rejection_reason=rejection_reason,
            )
            pending_scores.append((evaluation, bar_metrics, liquidity_score, bars))
            evaluations.append(evaluation)

    volume_values = [
        bar_metrics.mean_quote_volume
        for evaluation, bar_metrics, _liquidity_score, _bars in pending_scores
        if not evaluation.rejection_reason
    ]
    percentiles = volume_percentiles(volume_values)
    percentile_index = 0
    for evaluation, bar_metrics, liquidity_score, _bars in pending_scores:
        volume_percentile = None
        if not evaluation.rejection_reason:
            volume_percentile = percentiles[percentile_index]
            percentile_index += 1
        _merge_market_metrics_into_evaluation(
            evaluation,
            bar_metrics,
            liquidity_score=liquidity_score,
            volume_percentile=volume_percentile,
            set_composite_score=True,
        )

    body_config = {
        "exchange": venue,
        "resolutions": list(config.resolutions),
        "strategy_ids": [],
        "evaluate_strategies": False,
        "scan_kind": "market_opportunity",
        "months": config.months,
        "scoring": scoring_config_to_dict(config.scoring),
        "symbols_scanned": [entry.symbol_key for entry in tradable],
    }
    report = build_discovery_report(config=body_config, evaluations=evaluations)
    report["execution_costs"] = {
        "fee_rate": cost.fee_rate,
        "slippage_rate": cost.slippage_rate,
        "label": cost.label,
    }
    if config.out_dir is not None:
        config.out_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = config.out_dir / "discovery_report.json"
        artifact_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["artifact_path"] = str(artifact_path)
    return report


def _default_strategy_ids(exchange: str) -> list[str]:
    live_exchange = normalize_live_exchange(exchange)
    return [
        strategy_id
        for strategy_id in backtest_strategy_ids()
        if strategy_supported_on(strategy_id, live_exchange)
    ]


def run_opportunity_discovery(
    config: DiscoveryConfig,
    *,
    progress: Callable[[str], None] | None = None,
    fetch_bars: Callable[..., list[dict[str, Any]]] | None = None,
    discover_universe: Callable[..., list] | None = None,
) -> dict[str, Any]:
    log = progress or (lambda _message: None)
    venue = normalize_live_exchange(config.exchange)
    if venue != "hyperliquid":
        raise ValueError("v1 opportunity discovery supports hyperliquid only")

    universe_loader = discover_universe or discover_hyperliquid_perp_universe
    universe = universe_loader(
        symbols=config.symbols or None,
        resolution="60",
        filters=UniverseFilters(
            min_mean_volume_quote=config.min_mean_volume_quote,
            max_symbols=config.max_symbols,
        ),
    )
    tradable = [entry for entry in universe if entry.skipped_reason is None]
    if not tradable:
        raise ValueError("no tradable symbols after universe filters")

    fee_role: FeeRole = "taker" if config.fee_role != "maker" else "maker"
    cost = execution_cost_profile(venue, fee_role=fee_role, market_kind="perp")

    if not config.evaluate_strategies:
        return _run_market_liquidity_scan(
            config,
            tradable=tradable,
            venue=venue,
            cost=cost,
            log=log,
            fetch_bars=fetch_bars or fetch_history_bars,
        )

    strategy_ids = config.strategy_ids or _default_strategy_ids(venue)
    if not strategy_ids:
        raise ValueError("no strategies available for discovery")

    bars_loader = fetch_bars or fetch_history_bars
    evaluations: list = []
    total = len(tradable) * len(config.resolutions) * len(strategy_ids)
    step = 0

    for entry in tradable:
        liquidity_score = _liquidity_score_for_entry(
            entry,
            min_mean_volume_quote=config.min_mean_volume_quote,
        )

        for resolution in config.resolutions:
            log(f"discovery: loading {entry.symbol_key} {resolution} ({config.months}mo)")
            bars = bars_loader(
                exchange=venue,
                symbol_key=entry.symbol_key,
                resolution=resolution,
                months=config.months,
                use_cache=config.use_cache,
            )
            bars = filter_bars_for_job(
                bars,
                resolution=resolution,
                run_start_unix_seconds=config.run_start_unix_seconds,
                run_end_unix_seconds=config.run_end_unix_seconds,
            )
            market_fields = market_metrics_to_dict(compute_market_bar_metrics(bars))
            for strategy_id in strategy_ids:
                step += 1
                log(f"discovery: [{step}/{total}] {entry.symbol_key} {resolution} {strategy_id}")
                candidate = DiscoveryCandidate(
                    exchange=venue,
                    symbol_key=entry.symbol_key,
                    market_symbol=entry.market_symbol,
                    resolution=resolution,
                    strategy_id=strategy_id,
                    params_source="strategy_defaults",
                )
                try:
                    evaluation = evaluate_discovery_candidate(
                        candidate,
                        bars,
                        cost=cost,
                        cash=config.cash,
                        execution=config.execution,
                        min_bars=config.min_bars,
                        min_oos_bars=config.min_oos_bars,
                        liquidity_score=liquidity_score,
                    )
                    evaluation.metrics = {**market_fields, **evaluation.metrics}
                    evaluation = score_evaluation(evaluation, config.scoring)
                except Exception as exc:  # noqa: BLE001
                    from traderbot.discovery.candidate import CandidateEvaluation

                    log(
                        f"discovery: ERROR {entry.symbol_key} {resolution} {strategy_id}: "
                        f"{type(exc).__name__}: {exc}",
                    )
                    evaluation = CandidateEvaluation(
                        candidate=candidate,
                        regime_label="uncertain",
                        metrics=dict(market_fields),
                        walk_forward_stability=None,
                        liquidity_score=liquidity_score,
                        data_quality={"error": str(exc)},
                        rejection_reason=f"evaluation_error: {exc}",
                    )
                evaluations.append(evaluation)

    error_evaluations = [
        item
        for item in evaluations
        if (item.rejection_reason or "").startswith("evaluation_error")
    ]
    if error_evaluations:
        log(f"discovery: {len(error_evaluations)} evaluation error(s) — details above and in report rejected[]")

    body_config = {
        "exchange": venue,
        "resolutions": list(config.resolutions),
        "strategy_ids": strategy_ids,
        "evaluate_strategies": True,
        "scan_kind": "strategy_screen",
        "months": config.months,
        "cash": config.cash,
        "fee_role": config.fee_role,
        "execution": config.execution,
        "scoring": scoring_config_to_dict(config.scoring),
        "symbols_scanned": [entry.symbol_key for entry in tradable],
    }
    report = build_discovery_report(config=body_config, evaluations=evaluations)
    report["execution_costs"] = {
        "fee_rate": cost.fee_rate,
        "slippage_rate": cost.slippage_rate,
        "label": cost.label,
    }
    if config.out_dir is not None:
        config.out_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = config.out_dir / "discovery_report.json"
        artifact_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        report["artifact_path"] = str(artifact_path)
    return report
