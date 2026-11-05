from __future__ import annotations

import time
from typing import Any

from traderbot.analysis.correlation.aligner import align_candles_for_correlation
from traderbot.analysis.correlation.metrics import pearson_correlation, spearman_correlation
from traderbot.analysis.correlation.models import CorrelationMatrixResult


def compute_correlation_matrix(
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    *,
    timeframe: str = "60",
    min_observations: int = 10,
) -> CorrelationMatrixResult:
    """
    Generate NxN Pearson and Spearman correlation matrices of log-returns across an asset universe.
    Pairwise synchronization ensures asynchronous feeds are aligned without survivorship contamination.
    """
    symbols = sorted(bars_by_symbol.keys())
    n = len(symbols)
    now_ts = int(time.time())

    pearson_mat = [[0.0] * n for _ in range(n)]
    spearman_mat = [[0.0] * n for _ in range(n)]
    obs_mat = [[0] * n for _ in range(n)]

    for idx_a in range(n):
        pearson_mat[idx_a][idx_a] = 1.0
        spearman_mat[idx_a][idx_a] = 1.0
        obs_mat[idx_a][idx_a] = len(bars_by_symbol[symbols[idx_a]])

        for idx_b in range(idx_a + 1, n):
            sym_a = symbols[idx_a]
            sym_b = symbols[idx_b]
            aligned = align_candles_for_correlation(
                bars_by_symbol[sym_a],
                bars_by_symbol[sym_b],
                resolution=timeframe,
                min_observations=min_observations,
            )
            n_obs = len(aligned.returns_a)
            obs_mat[idx_a][idx_b] = n_obs
            obs_mat[idx_b][idx_a] = n_obs

            if n_obs >= 2:
                r = pearson_correlation(aligned.returns_a, aligned.returns_b)
                rho = spearman_correlation(aligned.returns_a, aligned.returns_b)
            else:
                r = 0.0
                rho = 0.0

            pearson_mat[idx_a][idx_b] = r
            pearson_mat[idx_b][idx_a] = r
            spearman_mat[idx_a][idx_b] = rho
            spearman_mat[idx_b][idx_a] = rho

    return CorrelationMatrixResult(
        symbols=symbols,
        timeframe=timeframe,
        pearson_matrix=pearson_mat,
        spearman_matrix=spearman_mat,
        observation_matrix=obs_mat,
        calculation_timestamp=now_ts,
    )

