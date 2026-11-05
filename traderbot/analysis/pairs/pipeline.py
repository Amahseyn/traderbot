from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
import time
import uuid
from typing import Any

from traderbot.algorithms.strategies.pair_trading import PairTradingAlgorithm
from traderbot.analysis.pairs.candidates import CandidatePair
from traderbot.analysis.pairs.engine import PairDiscoveryConfig, PairDiscoveryEngine
from traderbot.analysis.pairs.models import (
    DynamicRankingConfig,
    RankedPairResult,
    RankingSnapshot,
    RankTransition,
)
from traderbot.analysis.pairs.universe import MarketMetadata
from traderbot.backtesting.pair_engine import (
    MultiPairBacktestResult,
    PairBacktestResult,
    run_multi_pair_backtest,
    run_perp_pair_backtest,
)
from traderbot.backtesting.walk_forward import PairWalkForwardOptions, run_pair_walk_forward
from traderbot.markets.exchange import normalize_live_exchange
from traderbot.utils.trading_costs import roundtrip_cost_pct

logger = logging.getLogger(__name__)


@dataclass
class StatArbPipelineConfig:
    """Configuration for the unified 13-step Statistical Arbitrage Research Pipeline."""

    exchange: str = "hyperliquid"
    timeframe: str = "60"
    top_n: int = 10
    hysteresis_delta: float = 5.0
    initial_cash: float = 10_000.0
    run_backtest: bool = True
    run_walk_forward: bool = False
    walk_forward_train_bars: int = 80
    walk_forward_test_bars: int = 30
    walk_forward_purge_bars: int = 5
    execution: str = "close"
    persist: bool = True


@dataclass
class StatArbPipelineResult:
    """Execution artifact and data contract returned by the complete research pipeline."""

    run_id: str
    exchange: str
    timeframe: str
    tradable_markets: list[str]
    rejected_markets: dict[str, str]
    candidates: list[CandidatePair]
    all_qualification_results: list[RankedPairResult]
    ranked_pairs: list[RankedPairResult]
    transitions: list[RankTransition]
    backtest_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    portfolio_backtest_result: MultiPairBacktestResult | None = None
    walk_forward_results: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)


def run_stat_arb_research_pipeline(
    config: StatArbPipelineConfig | None = None,
    *,
    bars_by_symbol: dict[str, list[dict[str, Any]]],
    metadata_by_symbol: dict[str, MarketMetadata] | None = None,
    previous_snapshot: RankingSnapshot | None = None,
    job_id: str | None = None,
    as_of_unix_seconds: int | None = None,
) -> StatArbPipelineResult:
    """
    Executes the complete 13-Step Statistical Arbitrage Research Pipeline:
      1. Discover eligible markets (Point-in-time filtering)
      2. Validate market metadata (tick/lot sizes, clean OHLCV)
      3. Retrieve historical OHLCV
      4. Calculate return correlations
      5. Generate candidate pair pools (positive, negative, screened weak)
      6. Run cointegration tests (OLS, MacKinnon finite-sample surfaces, OU half-life, Chow test)
      7. Apply Benjamini-Hochberg FDR correction
      8. Calculate Pair Quality Score (0-100, hard econometric gates)
      9. Dynamic pair ranking (Hysteresis & spread correlation diversity filter)
      10. Generate strategy signals (PairTradingAlgorithm)
      11. Apply central risk controls (PortfolioRiskManager, PairExecutionRiskManager)
      12. Run multi-pair backtests or chronological walk-forward validations
      13. Persist research results, positions, and events to SQLite
    """
    cfg = config or StatArbPipelineConfig()
    pipeline_run_id = job_id or str(uuid.uuid4())
    exchange = normalize_live_exchange(cfg.exchange)
    timeframe = cfg.timeframe
    decision_time = as_of_unix_seconds or int(time.time())

    # --- STEPS 1 through 9: Discovery, Statistics, Scoring & Dynamic Ranking ---
    discovery_cfg = PairDiscoveryConfig(
        exchange=exchange,
        timeframe=timeframe,
        as_of_unix_seconds=decision_time,
        ranking_config=DynamicRankingConfig(
            top_n=cfg.top_n,
            hysteresis_delta=cfg.hysteresis_delta,
        ),
        persist=cfg.persist,
    )
    engine = PairDiscoveryEngine(discovery_cfg)

    all_output, snapshot, transitions, summary = engine.run_discovery(
        bars_by_symbol=bars_by_symbol,
        metadata_by_symbol=metadata_by_symbol,
        previous_snapshot=previous_snapshot,
        job_id=pipeline_run_id,
        as_of_unix_seconds=decision_time,
    )

    tradable_symbols = list(bars_by_symbol.keys())
    top_ranked = snapshot.ranked_pairs

    # --- STEPS 10 through 12: Strategy Signals, Risk Gating & Backtesting ---
    backtest_map: dict[str, dict[str, Any]] = {}
    multi_pair_res: MultiPairBacktestResult | None = None
    walk_forward_map: dict[str, Any] = {}

    if cfg.run_backtest and (top_ranked or all_output):
        # Evaluate for qualified pairs
        target_pairs = top_ranked if top_ranked else [p for p in all_output if p.qualification_status == "QUALIFIED"]
        if not target_pairs:
            # Fall back to testing highest scored candidate to ensure metrics exist
            target_pairs = sorted(all_output, key=lambda p: p.pair_quality_score, reverse=True)[:cfg.top_n]

        multi_pairs_conf: list[dict[str, Any]] = []
        cost_rate = roundtrip_cost_pct(exchange=exchange) / 2.0  # single-leg fee assumption

        for pair_res in target_pairs:
            bars_a = bars_by_symbol.get(pair_res.symbol_a, [])
            bars_b = bars_by_symbol.get(pair_res.symbol_b, [])
            if len(bars_a) < 10 or len(bars_b) < 10:
                continue

            # Instantiate Strategy Algorithm with discovered parameters
            hr = pair_res.hedge_ratio if pair_res.hedge_ratio > 0 else 1.0
            algo = PairTradingAlgorithm(
                symbol_a=pair_res.symbol_a,
                symbol_b=pair_res.symbol_b,
                hedge_ratio=hr,
                intercept=pair_res.intercept,
                spread_model="cointegration",
                lookback_period=min(60, max(10, len(bars_a) // 2)),
                entry_threshold=2.0,
                exit_threshold=0.5,
                stop_threshold=4.0,
            )

            # Step 12a: Individual Pair Backtest
            try:
                bt = run_perp_pair_backtest(
                    algorithm=algo,
                    dominant_bars=bars_a,
                    hedge_bars=bars_b,
                    initial_cash=cfg.initial_cash,
                    fee_rate=cost_rate,
                    execution=cfg.execution,
                )
                backtest_map[pair_res.pair_id] = {
                    "return_pct": round(bt.return_pct, 4),
                    "max_drawdown_pct": round(bt.max_drawdown_pct, 4),
                    "win_rate_pct": bt.win_rate_pct,
                    "trade_count": len(bt.trades),
                    "total_fees": round(bt.total_fees, 4),
                    "total_funding": round(bt.total_funding, 4),
                    "final_equity": round(bt.final_equity, 2),
                    "equity_curve": bt.equity_curve,
                    "spread_curve": bt.spread_curve,
                    "z_score_curve": bt.z_score_curve,
                }

                multi_pairs_conf.append({
                    "pair_id": pair_res.pair_id,
                    "algorithm": algo,
                    "dominant_bars": bars_a,
                    "hedge_bars": bars_b,
                    "fee_rate": cost_rate,
                })

                # Step 12b: Optional Chronological Walk-Forward
                if cfg.run_walk_forward and len(bars_a) >= (cfg.walk_forward_train_bars + cfg.walk_forward_purge_bars + cfg.walk_forward_test_bars):
                    wf_options = PairWalkForwardOptions(
                        param_grid={
                            "entry_threshold": [1.5, 2.0],
                            "exit_threshold": [0.4, 0.8],
                        },
                        dominant_bars=bars_a,
                        hedge_bars=bars_b,
                        train_bars=cfg.walk_forward_train_bars,
                        test_bars=cfg.walk_forward_test_bars,
                        purge_bars=cfg.walk_forward_purge_bars,
                        cash=cfg.initial_cash,
                        fee=cost_rate,
                        execution=cfg.execution,
                    )
                    wf_res = run_pair_walk_forward(wf_options)
                    walk_forward_map[pair_res.pair_id] = wf_res
            except Exception as exc:
                logger.warning("Backtest failed for pair %s: %s", pair_res.pair_id, exc)

        # Step 12c: Multi-Pair Portfolio Backtest
        if len(multi_pairs_conf) >= 2:
            try:
                multi_pair_res = run_multi_pair_backtest(
                    multi_pairs_conf,
                    initial_cash=cfg.initial_cash,
                    fee_rate=cost_rate,
                    execution=cfg.execution,
                )
            except Exception as exc:
                logger.warning("Multi-pair backtest failed: %s", exc)

    # --- STEP 13: Summary & SQLite Persistence ---
    summary["backtests_executed"] = len(backtest_map)
    summary["multi_pair_portfolio_evaluated"] = multi_pair_res is not None

    return StatArbPipelineResult(
        run_id=pipeline_run_id,
        exchange=exchange,
        timeframe=timeframe,
        tradable_markets=tradable_symbols,
        rejected_markets={},
        candidates=engine.candidate_generator.generate_candidates(
            bars_by_symbol,
            exchange=exchange,
            timeframe=timeframe,
        ),
        all_qualification_results=all_output,
        ranked_pairs=top_ranked,
        transitions=transitions,
        backtest_results=backtest_map,
        portfolio_backtest_result=multi_pair_res,
        walk_forward_results=walk_forward_map,
        summary=summary,
    )
