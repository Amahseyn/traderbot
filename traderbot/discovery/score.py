from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from traderbot.discovery.candidate import CandidateEvaluation


@dataclass
class ScoringConfig:
    weight_oos_return: float = 0.25
    weight_walk_forward_stability: float = 0.20
    weight_risk_adjusted: float = 0.15
    weight_drawdown: float = 0.15
    weight_regime_balance: float = 0.10
    weight_liquidity: float = 0.10
    weight_parameter_stability: float = 0.05
    min_trades: int = 5
    max_drawdown_pct: float = -40.0
    require_oos_return: bool = True
    require_walk_forward_stability: bool = True
    sharpe_cap: float = 3.0
    return_cap_pct: float = 100.0


DEFAULT_SCORING_CONFIG = ScoringConfig()


def _normalize_return(return_pct: float | None, cap: float) -> float | None:
    if return_pct is None or not math.isfinite(return_pct):
        return None
    if return_pct <= 0:
        return 0.0
    return min(1.0, return_pct / cap)


def _normalize_sharpe(sharpe: float | None, cap: float) -> float | None:
    if sharpe is None or not math.isfinite(sharpe):
        return None
    if sharpe <= 0:
        return 0.0
    return min(1.0, sharpe / cap)


def _normalize_drawdown(max_drawdown_pct: float | None, floor: float) -> float | None:
    if max_drawdown_pct is None or not math.isfinite(max_drawdown_pct):
        return None
    if max_drawdown_pct <= floor:
        return 0.0
    if max_drawdown_pct >= 0:
        return 1.0
    return min(1.0, max(0.0, 1.0 - abs(max_drawdown_pct - floor) / abs(floor)))


def _normalize_unit(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return min(1.0, max(0.0, value))


def eligibility_reason(evaluation: CandidateEvaluation, config: ScoringConfig) -> str | None:
    metrics = evaluation.metrics
    trade_count = int(metrics.get("trade_count") or 0)
    if trade_count < config.min_trades:
        return f"min_trades ({trade_count} < {config.min_trades})"
    drawdown = metrics.get("max_drawdown_pct")
    if drawdown is not None and float(drawdown) < config.max_drawdown_pct:
        return f"max_drawdown ({drawdown} < {config.max_drawdown_pct})"
    oos_return = metrics.get("oos_return_pct")
    if config.require_oos_return and oos_return is None:
        return "missing_oos_return"
    if evaluation.walk_forward_stability is None and config.require_walk_forward_stability:
        return "missing_walk_forward_stability"
    quality = evaluation.data_quality or {}
    if quality.get("insufficient_bars"):
        return "insufficient_bars"
    if quality.get("insufficient_oos_bars"):
        return "insufficient_oos_bars"
    return None


def score_evaluation(evaluation: CandidateEvaluation, config: ScoringConfig | None = None) -> CandidateEvaluation:
    cfg = config or DEFAULT_SCORING_CONFIG
    reason = eligibility_reason(evaluation, cfg)
    if reason:
        evaluation.rejection_reason = reason
        evaluation.component_scores = None
        evaluation.composite_score = None
        return evaluation

    metrics = evaluation.metrics
    components: dict[str, float | None] = {
        "oos_return": _normalize_return(metrics.get("oos_return_pct"), cfg.return_cap_pct),
        "walk_forward_stability": _normalize_unit(evaluation.walk_forward_stability),
        "risk_adjusted": _normalize_sharpe(metrics.get("sharpe_ratio"), cfg.sharpe_cap),
        "drawdown": _normalize_drawdown(metrics.get("max_drawdown_pct"), cfg.max_drawdown_pct),
        "regime_balance": _normalize_unit(metrics.get("regime_balance_score")),
        "liquidity": _normalize_unit(evaluation.liquidity_score),
        "parameter_stability": _normalize_unit(metrics.get("parameter_stability_score", 1.0)),
    }
    weights: dict[str, float] = {
        "oos_return": cfg.weight_oos_return,
        "walk_forward_stability": cfg.weight_walk_forward_stability,
        "risk_adjusted": cfg.weight_risk_adjusted,
        "drawdown": cfg.weight_drawdown,
        "regime_balance": cfg.weight_regime_balance,
        "liquidity": cfg.weight_liquidity,
        "parameter_stability": cfg.weight_parameter_stability,
    }
    active_weight = 0.0
    weighted_sum = 0.0
    scored: dict[str, float] = {}
    for name, weight in weights.items():
        value = components.get(name)
        if value is None:
            continue
        active_weight += weight
        weighted_sum += weight * value
        scored[name] = value
    if active_weight <= 0:
        evaluation.rejection_reason = "no_scorable_components"
        return evaluation
    evaluation.component_scores = scored
    evaluation.composite_score = round(weighted_sum / active_weight, 6)
    return evaluation


def scoring_config_from_dict(raw: dict[str, Any] | None) -> ScoringConfig:
    if not raw:
        return DEFAULT_SCORING_CONFIG
    fields = {key: value for key, value in raw.items() if hasattr(ScoringConfig, key)}
    base = ScoringConfig()
    for key, value in fields.items():
        setattr(base, key, value)
    return base


def scoring_config_to_dict(config: ScoringConfig) -> dict[str, Any]:
    from dataclasses import fields

    return {field.name: getattr(config, field.name) for field in fields(config)}
