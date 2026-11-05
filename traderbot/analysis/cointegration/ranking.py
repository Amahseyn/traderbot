from __future__ import annotations

import math
from typing import Any

from traderbot.algorithms.registry import pair_algorithm_for_id
from traderbot.analysis.cointegration.models import CointegrationResult, QualificationStatus
from traderbot.backtesting.pair_engine import PairBacktestResult, run_pair_backtest_for_exchange


def compute_pair_score(result: CointegrationResult, *, optimal_half_life_bars: float = 15.0) -> float:
    """
    Institutional multi-factor quality score for cointegrated pairs:
    Combines cointegration significance, hedge ratio stability, half-life optimality, and R^2.
    """
    if result.qualification_status == QualificationStatus.REJECTED.value:
        base_penalty = -10.0
    elif result.qualification_status == QualificationStatus.MARGINAL.value:
        base_penalty = 0.0
    else:
        base_penalty = 10.0

    sig_score = 1.0 - min(1.0, result.cointegration_pvalue)
    stability_score = max(0.0, min(1.0, result.hedge_ratio_stability))

    # Half-life bell curve: optimal around 15-20 bars
    hl = result.half_life_bars
    if hl is not None and hl > 0:
        hl_score = math.exp(-0.5 * (((hl - optimal_half_life_bars) / 10.0) ** 2))
    else:
        hl_score = 0.0

    r2_score = max(0.0, min(1.0, result.r_squared))

    composite = (
        base_penalty
        + 0.35 * sig_score
        + 0.25 * stability_score
        + 0.20 * hl_score
        + 0.20 * r2_score
    )
    return composite


def rank_cointegrated_pairs(
    results: list[CointegrationResult],
    *,
    top_n: int | None = None,
    optimal_half_life_bars: float = 15.0,
) -> list[CointegrationResult]:
    """
    Rank cointegrated pairs in descending order of institutional quality score.
    Qualified pairs with stable hedge ratios and optimal half-lives appear first.
    """
    scored = [
        (compute_pair_score(res, optimal_half_life_bars=optimal_half_life_bars), res)
        for res in results
    ]
    # Sort descending by score
    scored.sort(key=lambda item: item[0], reverse=True)
    sorted_results = [res for _, res in scored]

    if top_n is not None and top_n > 0:
        return sorted_results[:top_n]
    return sorted_results


def build_pair_trading_params(coint_result: CointegrationResult) -> dict[str, Any]:
    """
    Map cointegration econometric parameters into Traderbot PairTradingAlgorithm
    and pair backtest engine configurations.
    """
    hl = coint_result.half_life_bars or 10.0
    lookback = int(round(max(10, min(120, hl * 3.0))))

    return {
        "lookback_period": lookback,
        "entry_threshold": 2.0,
        "exit_threshold": 0.5,
        "hedge_ratio": coint_result.hedge_ratio,
        "pair_hedge_ratio": coint_result.hedge_ratio,
        "pair_lookback_period": lookback,
        "pair_entry_threshold": 2.0,
        "pair_exit_threshold": 0.5,
    }


def run_cointegrated_pair_backtest(
    coint_result: CointegrationResult,
    dominant_bars: list[dict[str, Any]],
    hedge_bars: list[dict[str, Any]],
    *,
    exchange: str = "hyperliquid",
    initial_cash: float = 10_000.0,
    fee_rate: float = 0.00045,
    slippage_rate: float = 0.0005,
) -> PairBacktestResult:
    """
    Execute a backtest on a cointegrated pair using Traderbot's existing pair backtest engine.
    Does not duplicate spread calculations or live execution.
    """
    params = build_pair_trading_params(coint_result)
    algo = pair_algorithm_for_id(
        "pair_trading",
        lookback_period=params["lookback_period"],
        entry_threshold=params["entry_threshold"],
        exit_threshold=params["exit_threshold"],
    )

    return run_pair_backtest_for_exchange(
        exchange,
        algo,
        dominant_bars,
        hedge_bars,
        fee_rate=fee_rate,
        slippage_rate=slippage_rate,
        hedge_ratio=abs(coint_result.hedge_ratio) if coint_result.hedge_ratio > 0 else 1.0,
        initial_cash=initial_cash,
    )
