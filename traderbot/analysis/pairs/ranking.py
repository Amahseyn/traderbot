from __future__ import annotations

import math
from typing import Any

import numpy as np

from traderbot.analysis.correlation.metrics import pearson_correlation
from traderbot.analysis.pairs.models import (
    DynamicRankingConfig,
    PairQualificationStatus,
    RankChangeType,
    RankedPairResult,
    RankingSnapshot,
    RankTransition,
)


def compute_spread_correlation(spread_a: list[float], spread_b: list[float]) -> float:
    """
    Compute Pearson correlation between two residual spread series of equal length.
    """
    if len(spread_a) != len(spread_b) or len(spread_a) < 10:
        min_len = min(len(spread_a), len(spread_b))
        if min_len < 10:
            return 0.0
        # Align tail
        sa = spread_a[-min_len:]
        sb = spread_b[-min_len:]
    else:
        sa = spread_a
        sb = spread_b

    return pearson_correlation(sa, sb)


class DynamicPairRanker:
    """
    Dynamic ranking engine with portfolio diversity constraints,
    spread correlation filtering, hysteresis churn prevention,
    minimum qualification durations, and rank transition tracking.
    """

    def __init__(self, config: DynamicRankingConfig | None = None) -> None:
        self.config = config or DynamicRankingConfig()

    def rank_pairs(
        self,
        candidate_results: list[RankedPairResult],
        previous_snapshot: RankingSnapshot | None = None,
        *,
        snapshot_timestamp: int = 0,
        exchange: str = "hyperliquid",
        timeframe: str = "60",
    ) -> tuple[list[RankedPairResult], RankingSnapshot, list[RankTransition]]:
        """
        Rank pairs and generate new snapshot with transition tracking.
        """
        # 1. Update qualification history
        prev_history: dict[str, int] = (
            dict(previous_snapshot.qualification_history) if previous_snapshot else {}
        )
        current_history: dict[str, int] = {}

        for pair in candidate_results:
            is_qual = pair.qualification_status == PairQualificationStatus.QUALIFIED.value
            prev_runs = prev_history.get(pair.pair_id, 0)
            current_history[pair.pair_id] = (prev_runs + 1) if is_qual else 0

        # Previous top-N pair lookup
        prev_rank_by_pair: dict[str, int] = {}
        if previous_snapshot:
            for p in previous_snapshot.ranked_pairs:
                if p.ranking_position is not None:
                    prev_rank_by_pair[p.pair_id] = p.ranking_position

        # 2. Filter qualified candidates and apply hysteresis scoring
        # Separate qualified from rejected
        qualified_candidates: list[RankedPairResult] = []
        rejected_candidates: list[RankedPairResult] = []

        for pair in candidate_results:
            if pair.qualification_status == PairQualificationStatus.QUALIFIED.value:
                # Check min qualification periods
                consec_runs = current_history.get(pair.pair_id, 0)
                if consec_runs >= self.config.min_qualification_periods:
                    qualified_candidates.append(pair)
                else:
                    reasons = list(pair.rejection_reasons) + [
                        f"probationary_qualification ({consec_runs} < {self.config.min_qualification_periods} runs)"
                    ]
                    rejected_candidates.append(
                        self._clone_with_rejection(pair, reasons)
                    )
            else:
                rejected_candidates.append(pair)

        # 3. Compute effective scores with hysteresis
        # Incumbents receive hysteresis bonus: score + hysteresis_delta
        scored_candidates: list[tuple[float, RankedPairResult]] = []
        for pair in qualified_candidates:
            is_incumbent = pair.pair_id in prev_rank_by_pair
            bonus = self.config.hysteresis_delta if is_incumbent else 0.0
            effective_score = pair.pair_quality_score + bonus
            scored_candidates.append((effective_score, pair))

        # Sort descending by effective score
        scored_candidates.sort(key=lambda item: item[0], reverse=True)

        # 4. Diversity Selection (Spread correlation & max symbol overlap)
        accepted_portfolio: list[RankedPairResult] = []
        symbol_counts: dict[str, int] = {}
        diversity_rejected: list[RankedPairResult] = []

        for effective_score, pair in scored_candidates:
            if len(accepted_portfolio) >= self.config.top_n:
                break

            sym_a = pair.symbol_a.upper()
            sym_b = pair.symbol_b.upper()

            # Check max symbol exposure limit
            count_a = symbol_counts.get(sym_a, 0)
            count_b = symbol_counts.get(sym_b, 0)
            if (
                count_a >= self.config.max_pairs_per_symbol
                or count_b >= self.config.max_pairs_per_symbol
            ):
                reasons = list(pair.rejection_reasons) + [
                    f"diversity_symbol_overlap (max {self.config.max_pairs_per_symbol} pairs for {sym_a} or {sym_b})"
                ]
                diversity_rejected.append(self._clone_with_rejection(pair, reasons))
                continue

            # Check residual spread correlation against already accepted pairs
            spread_corr_violation = False
            violating_pair_id = ""
            for acc in accepted_portfolio:
                if pair.residual_spread and acc.residual_spread:
                    rho_spread = abs(
                        compute_spread_correlation(pair.residual_spread, acc.residual_spread)
                    )
                    if rho_spread > self.config.diversity_spread_corr_max:
                        spread_corr_violation = True
                        violating_pair_id = acc.pair_id
                        break

            if spread_corr_violation:
                reasons = list(pair.rejection_reasons) + [
                    f"excessive_spread_correlation (|corr| > {self.config.diversity_spread_corr_max:.2f} with {violating_pair_id})"
                ]
                diversity_rejected.append(self._clone_with_rejection(pair, reasons))
                continue

            # Accept into top portfolio
            symbol_counts[sym_a] = count_a + 1
            symbol_counts[sym_b] = count_b + 1
            accepted_portfolio.append(pair)

        # 5. Assign 1-based ranking positions to accepted pairs
        final_ranked_pairs: list[RankedPairResult] = []
        current_rank_by_pair: dict[str, int] = {}
        for rank_idx, pair in enumerate(accepted_portfolio, start=1):
            current_rank_by_pair[pair.pair_id] = rank_idx
            ranked = RankedPairResult(
                pair_id=pair.pair_id,
                exchange=pair.exchange,
                symbol_a=pair.symbol_a,
                symbol_b=pair.symbol_b,
                timeframe=pair.timeframe,
                correlation=pair.correlation,
                cointegration_status=pair.cointegration_status,
                hedge_ratio=pair.hedge_ratio,
                half_life_bars=pair.half_life_bars,
                liquidity_score=pair.liquidity_score,
                stability_score=pair.stability_score,
                pair_quality_score=pair.pair_quality_score,
                ranking_position=rank_idx,
                qualification_status=pair.qualification_status,
                rejection_reasons=pair.rejection_reasons,
                last_updated=snapshot_timestamp or pair.last_updated,
                cointegration_pvalue=pair.cointegration_pvalue,
                adf_statistic=pair.adf_statistic,
                adjusted_pvalue=pair.adjusted_pvalue,
                spread_std=pair.spread_std,
                spread_mean=pair.spread_mean,
                r_squared=pair.r_squared,
                score_breakdown=pair.score_breakdown,
                residual_spread=pair.residual_spread,
            )
            final_ranked_pairs.append(ranked)

        # Remaining unranked qualified pairs
        accepted_ids = set(current_rank_by_pair.keys())
        unranked_qualified: list[RankedPairResult] = []
        for pair in qualified_candidates:
            if pair.pair_id not in accepted_ids and pair.pair_id not in {d.pair_id for d in diversity_rejected}:
                unranked_qualified.append(
                    self._clone_with_rank(pair, None)
                )

        # 6. Rank Transition Tracking
        transitions: list[RankTransition] = []

        # Check all pairs in current ranking
        for pair in final_ranked_pairs:
            new_r = pair.ranking_position
            old_r = prev_rank_by_pair.get(pair.pair_id)
            if old_r is None:
                transitions.append(
                    RankTransition(
                        pair_id=pair.pair_id,
                        previous_rank=None,
                        new_rank=new_r,
                        change_type=RankChangeType.NEW_ENTRY,
                        reason=f"Entered top-{self.config.top_n} at position #{new_r}",
                    )
                )
            elif old_r == new_r:
                transitions.append(
                    RankTransition(
                        pair_id=pair.pair_id,
                        previous_rank=old_r,
                        new_rank=new_r,
                        change_type=RankChangeType.UNCHANGED,
                        reason=f"Retained position #{new_r}",
                    )
                )
            elif new_r < old_r:
                transitions.append(
                    RankTransition(
                        pair_id=pair.pair_id,
                        previous_rank=old_r,
                        new_rank=new_r,
                        change_type=RankChangeType.PROMOTION,
                        reason=f"Promoted from #{old_r} to #{new_r}",
                    )
                )
            else:
                transitions.append(
                    RankTransition(
                        pair_id=pair.pair_id,
                        previous_rank=old_r,
                        new_rank=new_r,
                        change_type=RankChangeType.DEMOTION,
                        reason=f"Demoted from #{old_r} to #{new_r}",
                    )
                )

        # Check exits from previous top-N
        for prev_pair_id, old_r in prev_rank_by_pair.items():
            if prev_pair_id not in current_rank_by_pair:
                # Find exit reason
                reason = "Displaced by higher scoring candidate"
                for r in rejected_candidates + diversity_rejected:
                    if r.pair_id == prev_pair_id:
                        reason = "; ".join(r.rejection_reasons) or "Disqualified"
                        break
                transitions.append(
                    RankTransition(
                        pair_id=prev_pair_id,
                        previous_rank=old_r,
                        new_rank=None,
                        change_type=RankChangeType.EXIT,
                        reason=f"Exited from rank #{old_r}: {reason}",
                    )
                )

        # 7. Construct Snapshot
        snapshot = RankingSnapshot(
            snapshot_timestamp=snapshot_timestamp,
            exchange=exchange,
            timeframe=timeframe,
            ranked_pairs=final_ranked_pairs,
            qualification_history=current_history,
        )

        all_output = final_ranked_pairs + unranked_qualified + diversity_rejected + rejected_candidates
        return all_output, snapshot, transitions

    @staticmethod
    def _clone_with_rejection(pair: RankedPairResult, reasons: list[str]) -> RankedPairResult:
        return RankedPairResult(
            pair_id=pair.pair_id,
            exchange=pair.exchange,
            symbol_a=pair.symbol_a,
            symbol_b=pair.symbol_b,
            timeframe=pair.timeframe,
            correlation=pair.correlation,
            cointegration_status=pair.cointegration_status,
            hedge_ratio=pair.hedge_ratio,
            half_life_bars=pair.half_life_bars,
            liquidity_score=pair.liquidity_score,
            stability_score=pair.stability_score,
            pair_quality_score=0.0,
            ranking_position=None,
            qualification_status=PairQualificationStatus.REJECTED.value,
            rejection_reasons=reasons,
            last_updated=pair.last_updated,
            cointegration_pvalue=pair.cointegration_pvalue,
            adf_statistic=pair.adf_statistic,
            adjusted_pvalue=pair.adjusted_pvalue,
            spread_std=pair.spread_std,
            spread_mean=pair.spread_mean,
            r_squared=pair.r_squared,
            score_breakdown=pair.score_breakdown,
            residual_spread=pair.residual_spread,
        )

    @staticmethod
    def _clone_with_rank(pair: RankedPairResult, rank: int | None) -> RankedPairResult:
        return RankedPairResult(
            pair_id=pair.pair_id,
            exchange=pair.exchange,
            symbol_a=pair.symbol_a,
            symbol_b=pair.symbol_b,
            timeframe=pair.timeframe,
            correlation=pair.correlation,
            cointegration_status=pair.cointegration_status,
            hedge_ratio=pair.hedge_ratio,
            half_life_bars=pair.half_life_bars,
            liquidity_score=pair.liquidity_score,
            stability_score=pair.stability_score,
            pair_quality_score=pair.pair_quality_score,
            ranking_position=rank,
            qualification_status=pair.qualification_status,
            rejection_reasons=pair.rejection_reasons,
            last_updated=pair.last_updated,
            cointegration_pvalue=pair.cointegration_pvalue,
            adf_statistic=pair.adf_statistic,
            adjusted_pvalue=pair.adjusted_pvalue,
            spread_std=pair.spread_std,
            spread_mean=pair.spread_mean,
            r_squared=pair.r_squared,
            score_breakdown=pair.score_breakdown,
            residual_spread=pair.residual_spread,
        )

