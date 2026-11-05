from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from traderbot.analysis.cointegration.models import (
    CointegrationThresholds,
    QualificationStatus,
)
from traderbot.analysis.pairs.candidates import CandidatePairGenerator
from traderbot.analysis.pairs.models import (
    CandidatePair,
    CandidatePairCriteria,
    DynamicRankingConfig,
    MarketUniverseFilter,
    PairQualityWeights,
    RankedPairResult,
    RankingSnapshot,
    RankTransition,
)
from traderbot.analysis.pairs.persistence import record_pair_discovery_run
from traderbot.analysis.pairs.qualification import CointegrationQualifier
from traderbot.analysis.pairs.ranking import DynamicPairRanker
from traderbot.analysis.pairs.scoring import PairQualityScorer
from traderbot.analysis.pairs.universe import (
    MarketMetadata,
    discover_tradable_universe,
)
from traderbot.markets.exchange import normalize_live_exchange
from traderbot.utils.trading_costs import roundtrip_cost_pct


@dataclass
class PairDiscoveryConfig:
    exchange: str = "hyperliquid"
    timeframe: str = "60"
    universe_filter: MarketUniverseFilter = field(default_factory=MarketUniverseFilter)
    candidate_criteria: CandidatePairCriteria = field(default_factory=CandidatePairCriteria)
    cointegration_thresholds: CointegrationThresholds = field(default_factory=CointegrationThresholds)
    quality_weights: PairQualityWeights = field(default_factory=PairQualityWeights)
    ranking_config: DynamicRankingConfig = field(default_factory=DynamicRankingConfig)
    as_of_unix_seconds: int | None = None
    roundtrip_cost: float | None = None
    persist: bool = True


class PairDiscoveryEngine:
    """
    Dynamic Cryptocurrency Pair Discovery and Ranking Engine.
    Executes universe filtering, candidate generation, cointegration qualification,
    0-100 quality scoring, dynamic ranking with hysteresis, and SQLite persistence.
    """

    def __init__(self, config: PairDiscoveryConfig | None = None) -> None:
        self.config = config or PairDiscoveryConfig()
        self.candidate_generator = CandidatePairGenerator(criteria=self.config.candidate_criteria)
        self.qualifier = CointegrationQualifier(thresholds=self.config.cointegration_thresholds)
        self.scorer = PairQualityScorer(weights=self.config.quality_weights)
        self.ranker = DynamicPairRanker(config=self.config.ranking_config)

    def run_discovery(
        self,
        bars_by_symbol: dict[str, list[dict[str, Any]]],
        metadata_by_symbol: dict[str, MarketMetadata] | None = None,
        previous_snapshot: RankingSnapshot | None = None,
        *,
        job_id: str | None = None,
        as_of_unix_seconds: int | None = None,
    ) -> tuple[list[RankedPairResult], RankingSnapshot, list[RankTransition], dict[str, Any]]:
        """
        Execute the complete discovery, qualification, scoring, and ranking pipeline.
        """
        start_time = time.time()
        decision_time = as_of_unix_seconds or self.config.as_of_unix_seconds or int(time.time())
        exchange = normalize_live_exchange(self.config.exchange)
        timeframe = self.config.timeframe

        # 1. Market Universe Discovery & Point-in-Time Filtering
        tradable_bars, rejected_markets = discover_tradable_universe(
            exchange=exchange,
            bars_by_symbol=bars_by_symbol,
            metadata_by_symbol=metadata_by_symbol,
            filter_config=self.config.universe_filter,
            as_of_unix_seconds=decision_time,
            resolution=timeframe,
        )

        # 2. Candidate Pair Generation
        candidates = self.candidate_generator.generate_candidates(
            tradable_bars,
            exchange=exchange,
            timeframe=timeframe,
        )

        # 3. Cointegration Qualification
        cost = self.config.roundtrip_cost or roundtrip_cost_pct(exchange=exchange)
        coint_results = self.qualifier.qualify_candidates(
            candidates,
            tradable_bars,
            exchange=exchange,
            timeframe=timeframe,
            roundtrip_cost=cost,
        )

        # 4. Multi-Factor Pair Quality Scoring (0 to 100) & Hard Rejection
        meta_map = metadata_by_symbol or {}
        scored_pairs: list[RankedPairResult] = []

        for cand in candidates:
            c_res = coint_results.get(cand.pair_id)
            if c_res is None:
                continue

            bars_a = tradable_bars.get(cand.symbol_a, [])
            bars_b = tradable_bars.get(cand.symbol_b, [])
            meta_a = meta_map.get(cand.symbol_a)
            meta_b = meta_map.get(cand.symbol_b)

            score, breakdown, rejection_reasons = self.scorer.score_pair(
                candidate=cand,
                coint_result=c_res,
                bars_a=bars_a,
                bars_b=bars_b,
                meta_a=meta_a,
                meta_b=meta_b,
                roundtrip_cost=cost or 0.0019,
            )

            # Compute residual spread series for diversity check
            # s_t = ln(P_A) - alpha - beta * ln(P_B)
            aligned_len = min(len(bars_a), len(bars_b))
            if aligned_len >= 10:
                import numpy as np

                ca = [float(b["close"]) for b in bars_a[-aligned_len:]]
                cb = [float(b["close"]) for b in bars_b[-aligned_len:]]
                residual_spread = list(
                    np.log(ca) - c_res.intercept - (c_res.hedge_ratio * np.log(cb))
                )
            else:
                residual_spread = []

            pair_res = RankedPairResult(
                pair_id=cand.pair_id,
                exchange=exchange,
                symbol_a=cand.symbol_a,
                symbol_b=cand.symbol_b,
                timeframe=timeframe,
                correlation=cand.correlation,
                cointegration_status=c_res.stationarity_status,
                hedge_ratio=c_res.hedge_ratio,
                half_life_bars=c_res.half_life_bars,
                liquidity_score=breakdown.liquidity_score,
                stability_score=breakdown.hedge_ratio_stability_score,
                pair_quality_score=score,
                ranking_position=None,
                qualification_status=c_res.qualification_status,
                rejection_reasons=rejection_reasons,
                last_updated=decision_time,
                cointegration_pvalue=c_res.cointegration_pvalue,
                adf_statistic=c_res.adf_statistic,
                adjusted_pvalue=c_res.adjusted_pvalue,
                spread_std=c_res.spread_std,
                spread_mean=c_res.spread_mean,
                intercept=c_res.intercept,
                r_squared=c_res.r_squared,
                score_breakdown=breakdown,
                residual_spread=residual_spread,
            )
            scored_pairs.append(pair_res)

        # 5. Dynamic Ranking with Hysteresis & Diversity Filtering
        all_output, snapshot, transitions = self.ranker.rank_pairs(
            candidate_results=scored_pairs,
            previous_snapshot=previous_snapshot,
            snapshot_timestamp=decision_time,
            exchange=exchange,
            timeframe=timeframe,
        )

        elapsed = time.time() - start_time
        top_pairs = snapshot.ranked_pairs

        # Summary statistics
        summary = {
            "exchange": exchange,
            "timeframe": timeframe,
            "total_markets_scanned": len(bars_by_symbol),
            "tradable_markets": len(tradable_bars),
            "rejected_markets": len(rejected_markets),
            "candidates_generated": len(candidates),
            "candidates_qualified": sum(
                1 for p in all_output if p.qualification_status == QualificationStatus.QUALIFIED.value
            ),
            "candidates_rejected": sum(
                1 for p in all_output if p.qualification_status == QualificationStatus.REJECTED.value
            ),
            "top_ranked_count": len(top_pairs),
            "top_pairs": [p.pair_id for p in top_pairs],
            "elapsed_seconds": round(elapsed, 4),
        }

        # 6. SQLite Persistence
        if self.config.persist:
            record_pair_discovery_run(
                job_id=job_id,
                exchange=exchange,
                timeframe=timeframe,
                config={
                    "exchange": exchange,
                    "timeframe": timeframe,
                    "as_of_unix_seconds": decision_time,
                    "top_n": self.config.ranking_config.top_n,
                    "hysteresis_delta": self.config.ranking_config.hysteresis_delta,
                },
                summary=summary,
                candidates=candidates,
                ranked_pairs=all_output,
                transitions=transitions,
                snapshot=snapshot,
            )

        return all_output, snapshot, transitions, summary

