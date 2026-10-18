from traderbot.discovery.candidate import CandidateEvaluation, DiscoveryCandidate
from traderbot.discovery.score import ScoringConfig, eligibility_reason, score_evaluation


def _evaluation(**metrics: object) -> CandidateEvaluation:
    candidate = DiscoveryCandidate(
        exchange="hyperliquid",
        symbol_key="btc",
        market_symbol="BTCUSDT",
        resolution="60",
        strategy_id="sma_cross",
        params_source="defaults",
    )
    return CandidateEvaluation(
        candidate=candidate,
        regime_label="trending",
        metrics={
            "trade_count": 10,
            "max_drawdown_pct": -12.0,
            "oos_return_pct": 5.0,
            "sharpe_ratio": 1.2,
            **metrics,
        },
        walk_forward_stability=0.75,
        liquidity_score=0.8,
        data_quality={},
    )


def test_eligibility_rejects_low_trades() -> None:
    evaluation = _evaluation(trade_count=2)
    reason = eligibility_reason(evaluation, ScoringConfig(min_trades=5))
    assert reason is not None
    assert "min_trades" in reason


def test_score_evaluation_sets_composite() -> None:
    evaluation = score_evaluation(_evaluation())
    assert evaluation.rejection_reason is None
    assert evaluation.composite_score is not None
    assert 0.0 <= evaluation.composite_score <= 1.0
    assert evaluation.component_scores is not None


def test_missing_oos_return_rejected_when_required() -> None:
    evaluation = _evaluation(oos_return_pct=None)
    evaluation = score_evaluation(evaluation, ScoringConfig(require_oos_return=True))
    assert evaluation.rejection_reason == "missing_oos_return"
