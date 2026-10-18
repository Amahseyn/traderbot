from __future__ import annotations

from typing import Any

from traderbot.discovery.candidate import CandidateEvaluation


def evaluation_to_row(evaluation: CandidateEvaluation) -> dict[str, Any]:
    candidate = evaluation.candidate
    metrics = evaluation.metrics
    return {
        "exchange": candidate.exchange,
        "symbol_key": candidate.symbol_key,
        "market_symbol": candidate.market_symbol,
        "resolution": candidate.resolution,
        "strategy_id": candidate.strategy_id or None,
        "params_source": candidate.params_source,
        "regime_label": evaluation.regime_label,
        "composite_score": evaluation.composite_score,
        "component_scores": evaluation.component_scores,
        "oos_return_pct": metrics.get("oos_return_pct"),
        "sharpe_ratio": metrics.get("sharpe_ratio"),
        "max_drawdown_pct": metrics.get("max_drawdown_pct"),
        "trade_count": metrics.get("trade_count"),
        "mean_quote_volume": metrics.get("mean_quote_volume"),
        "volume_percentile": metrics.get("volume_percentile"),
        "return_1bar_pct": metrics.get("return_1bar_pct"),
        "return_7bar_pct": metrics.get("return_7bar_pct"),
        "return_30bar_pct": metrics.get("return_30bar_pct"),
        "realized_vol_pct": metrics.get("realized_vol_pct"),
        "range_pct_1bar": metrics.get("range_pct_1bar"),
        "atr_pct": metrics.get("atr_pct"),
        "estimated_transaction_costs": metrics.get("estimated_transaction_costs"),
        "walk_forward_stability": evaluation.walk_forward_stability,
        "liquidity_score": evaluation.liquidity_score,
        "validation_status": "rejected" if evaluation.rejection_reason else "eligible",
        "rejection_reason": evaluation.rejection_reason,
        "data_quality": evaluation.data_quality,
        "metrics": metrics,
    }


def build_discovery_report(
    *,
    config: dict[str, Any],
    evaluations: list[CandidateEvaluation],
) -> dict[str, Any]:
    rows = [evaluation_to_row(item) for item in evaluations]
    eligible = [row for row in rows if row["validation_status"] == "eligible"]
    rejected = [row for row in rows if row["validation_status"] == "rejected"]
    eligible.sort(
        key=lambda row: (
            row.get("composite_score") is None,
            -(float(row["composite_score"]) if row.get("composite_score") is not None else 0.0),
        ),
    )
    for rank, row in enumerate(eligible, start=1):
        row["rank"] = rank
    return {
        "config": config,
        "summary": {
            "candidates_evaluated": len(rows),
            "candidates_eligible": len(eligible),
            "candidates_rejected": len(rejected),
        },
        "ranked": eligible,
        "rejected": rejected,
    }
