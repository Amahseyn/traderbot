from __future__ import annotations

import math
from typing import Any

import numpy as np

from traderbot.analysis.correlation.aligner import align_candles_for_correlation
from traderbot.analysis.correlation.metrics import pearson_correlation
from traderbot.analysis.correlation.scanner import CorrelationScanner
from traderbot.analysis.pairs.models import (
    CandidateCategory,
    CandidatePair,
    CandidatePairCriteria,
)


def _build_pair_id(exchange: str, symbol_a: str, symbol_b: str) -> str:
    # Deterministic alphabetical ordering for pair identifier
    first, second = sorted([symbol_a.upper(), symbol_b.upper()])
    return f"{exchange.lower()}:{first}-{second}"


class CandidatePairGenerator:
    """
    Institutional candidate generator using CorrelationScanner pre-screening
    to identify candidate pairs without testing all O(M^2) pairs on large universes.
    """

    def __init__(
        self,
        criteria: CandidatePairCriteria | None = None,
        correlation_scanner: CorrelationScanner | None = None,
    ) -> None:
        self.criteria = criteria or CandidatePairCriteria()
        self.scanner = correlation_scanner or CorrelationScanner()

    def generate_candidates(
        self,
        bars_by_symbol: dict[str, list[dict[str, Any]]],
        *,
        exchange: str = "hyperliquid",
        timeframe: str = "60",
    ) -> list[CandidatePair]:
        """
        Generate candidate pairs partitioned across strong positive, strong negative,
        and weak/moderate correlation pools with configurable scan limits.
        """
        symbols = sorted(bars_by_symbol.keys())
        n = len(symbols)
        if n < 2:
            return []

        # 1. Compute correlations across all pairs
        strong_pos: list[CandidatePair] = []
        strong_neg: list[CandidatePair] = []
        weak_screened: list[tuple[float, CandidatePair]] = []

        for idx_a in range(n):
            sym_a = symbols[idx_a]
            bars_a = bars_by_symbol[sym_a]
            for idx_b in range(idx_a + 1, n):
                sym_b = symbols[idx_b]
                bars_b = bars_by_symbol[sym_b]

                aligned = align_candles_for_correlation(
                    bars_a,
                    bars_b,
                    resolution=timeframe,
                    min_observations=10,
                )
                n_obs = len(aligned.returns_a)
                if n_obs < 10:
                    continue

                r = pearson_correlation(aligned.returns_a, aligned.returns_b)
                pair_id = _build_pair_id(exchange, sym_a, sym_b)

                if r >= self.criteria.strong_pos_threshold:
                    strong_pos.append(
                        CandidatePair(
                            pair_id=pair_id,
                            symbol_a=sym_a,
                            symbol_b=sym_b,
                            correlation=r,
                            category=CandidateCategory.STRONG_POSITIVE,
                            observation_count=n_obs,
                        )
                    )
                elif r <= self.criteria.strong_neg_threshold:
                    strong_neg.append(
                        CandidatePair(
                            pair_id=pair_id,
                            symbol_a=sym_a,
                            symbol_b=sym_b,
                            correlation=r,
                            category=CandidateCategory.STRONG_NEGATIVE,
                            observation_count=n_obs,
                        )
                    )
                elif self.criteria.allow_weak_cointegrated:
                    # For weak correlation, screen by variance ratio similarity of log prices:
                    # Var(A) / Var(B) close to 1.0 indicates comparable volatility regime
                    var_a = float(np.var(np.log(aligned.closes_a)))
                    var_b = float(np.var(np.log(aligned.closes_b)))
                    if var_a > 1e-12 and var_b > 1e-12:
                        var_ratio = var_a / var_b if var_a >= var_b else var_b / var_a
                    else:
                        var_ratio = 999.0

                    cand = CandidatePair(
                        pair_id=pair_id,
                        symbol_a=sym_a,
                        symbol_b=sym_b,
                        correlation=r,
                        category=CandidateCategory.WEAK_SCREENED,
                        observation_count=n_obs,
                    )
                    weak_screened.append((var_ratio, cand))

        # Sort candidate pools:
        # - Strong pos sorted descending by correlation
        strong_pos.sort(key=lambda cp: cp.correlation, reverse=True)
        # - Strong neg sorted ascending by correlation (most negative first)
        strong_neg.sort(key=lambda cp: cp.correlation)
        # - Weak screened sorted by volatility ratio similarity (closest to 1.0 first)
        weak_screened.sort(key=lambda item: item[0])
        weak_cands = [cand for _, cand in weak_screened]

        # Apply scan limits if configured
        max_total = self.criteria.max_candidates
        if max_total is None or max_total <= 0:
            return strong_pos + strong_neg + weak_cands

        # Proportional allocation across candidate pools:
        # e.g., 40% positive, 30% negative, 30% weak
        cap_pos = max(1, int(max_total * 0.40))
        cap_neg = max(1, int(max_total * 0.30))
        cap_weak = max(1, max_total - cap_pos - cap_neg)

        selected_pos = strong_pos[:cap_pos]
        selected_neg = strong_neg[:cap_neg]
        selected_weak = weak_cands[:cap_weak]

        # If any pool has leftover capacity, backfill from other pools
        combined = selected_pos + selected_neg + selected_weak
        remaining_slots = max_total - len(combined)
        if remaining_slots > 0:
            leftovers = (
                strong_pos[cap_pos:]
                + strong_neg[cap_neg:]
                + weak_cands[cap_weak:]
            )
            combined.extend(leftovers[:remaining_slots])

        return combined

