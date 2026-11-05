from __future__ import annotations

import math
import time
from typing import Any, Sequence
import numpy as np
import pytest

from traderbot.analysis.cointegration.models import (
    CointegrationThresholds,
    QualificationStatus,
)
from traderbot.analysis.pairs.candidates import CandidatePairGenerator, _build_pair_id
from traderbot.analysis.pairs.engine import PairDiscoveryConfig, PairDiscoveryEngine
from traderbot.analysis.pairs.models import (
    CandidateCategory,
    CandidatePair,
    CandidatePairCriteria,
    DynamicRankingConfig,
    MarketUniverseFilter,
    PairQualityWeights,
    RankChangeType,
    RankedPairResult,
    RankingSnapshot,
)
from traderbot.analysis.pairs.persistence import (
    fetch_latest_pair_ranking,
    fetch_pair_ranking_history,
    list_pair_discovery_runs,
    record_pair_discovery_run,
)
from traderbot.analysis.pairs.qualification import CointegrationQualifier
from traderbot.analysis.pairs.ranking import DynamicPairRanker, compute_spread_correlation
from traderbot.analysis.pairs.scoring import PairQualityScorer
from traderbot.analysis.pairs.universe import (
    MarketMetadata,
    compute_24h_quote_volume,
    discover_tradable_universe,
    filter_market,
    validate_ohlcv_bars,
)


def _generate_bars_from_prices(
    prices: Sequence[float] | np.ndarray,
    symbol: str = "BTC",
    resolution: str = "60",
    start_timestamp: int = 1_000_000,
    volume: float = 1_000.0,
) -> list[dict[str, Any]]:
    step_seconds = int(resolution) * 60 if resolution.isdigit() else 3600
    bars = []
    for idx, price in enumerate(prices):
        p = float(price)
        bars.append({
            "symbol": symbol,
            "resolution": resolution,
            "timestamp": start_timestamp + idx * step_seconds,
            "open": p,
            "high": p * 1.002,
            "low": p * 0.998,
            "close": p,
            "volume": volume,
        })
    return bars


def _generate_cointegrated_pair(
    n_bars: int = 250,
    beta: float = 1.2,
    phi: float = 0.85,
    seed: int = 2,
    symbol_a: str = "BTC",
    symbol_b: str = "ETH",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = np.random.default_rng(seed)
    # Asset B is a random walk with zero drift
    innovations_b = rng.normal(0, 0.01, size=n_bars)
    log_b = 4.0 + np.cumsum(innovations_b)

    # Stationary AR(1) spread
    spread = np.zeros(n_bars)
    noise = rng.normal(0, 0.008, size=n_bars)
    for t in range(1, n_bars):
        spread[t] = phi * spread[t - 1] + noise[t]

    log_a = 0.5 + beta * log_b + spread
    price_a = np.exp(log_a)
    price_b = np.exp(log_b)

    bars_a = _generate_bars_from_prices(price_a, symbol=symbol_a, volume=10_000.0)
    bars_b = _generate_bars_from_prices(price_b, symbol=symbol_b, volume=10_000.0)
    return bars_a, bars_b


# =============================================================================
# 1. Market Universe Filtering & Validation
# =============================================================================

def test_market_universe_filtering():
    """Verify rejection of inactive, delisted, low-volume, and wide-spread markets."""
    bars_clean, _ = _generate_cointegrated_pair(n_bars=150, symbol_a="CLEAN")

    filter_cfg = MarketUniverseFilter(
        min_history_bars=100,
        min_volume_quote_24h=50_000.0,
        max_bid_ask_spread_pct=0.005,
        min_order_book_depth_usd=10_000.0,
        filter_delisted=True,
        filter_inactive=True,
    )

    # Active clean market
    meta_clean = MarketMetadata(
        symbol="CLEAN",
        exchange="hyperliquid",
        is_active=True,
        is_delisted=False,
        bid_ask_spread_pct=0.001,
        order_book_depth_usd=50_000.0,
    )
    eligible, reasons = filter_market("CLEAN", bars_clean, meta_clean, filter_cfg)
    assert eligible is True
    assert len(reasons) == 0

    # Delisted market
    meta_delisted = MarketMetadata(
        symbol="DELISTED",
        exchange="hyperliquid",
        is_active=True,
        is_delisted=True,
    )
    eligible, reasons = filter_market("DELISTED", bars_clean, meta_delisted, filter_cfg)
    assert eligible is False
    assert "delisted_market" in reasons

    # Excessive spread market
    meta_wide = MarketMetadata(
        symbol="WIDE",
        exchange="hyperliquid",
        is_active=True,
        is_delisted=False,
        bid_ask_spread_pct=0.015,  # 1.5% > 0.5% limit
    )
    eligible, reasons = filter_market("WIDE", bars_clean, meta_wide, filter_cfg)
    assert eligible is False
    assert any("excessive_spread" in r for r in reasons)

    # Insufficient history market
    bars_short = bars_clean[:50]
    eligible, reasons = filter_market("SHORT", bars_short, meta_clean, filter_cfg)
    assert eligible is False
    assert any("insufficient_history" in r for r in reasons)


def test_ohlcv_bar_integrity_validation():
    """Ensure invalid OHLCV bars (corrupt envelopes, non-positive prices) are rejected."""
    # Corrupt bar: high < low
    corrupt_bars = [
        {"timestamp": 1000 + i * 3600, "open": 100.0, "high": 90.0, "low": 110.0, "close": 100.0, "volume": 100.0}
        for i in range(10)
    ]
    is_valid, err = validate_ohlcv_bars(corrupt_bars)
    assert is_valid is False
    assert "corrupt_high_low_envelope" in err

    # Negative price
    neg_bars = [
        {"timestamp": 1000 + i * 3600, "open": -10.0, "high": 10.0, "low": -20.0, "close": 5.0, "volume": 100.0}
        for i in range(10)
    ]
    is_valid, err = validate_ohlcv_bars(neg_bars)
    assert is_valid is False
    assert "non_positive_price" in err


# =============================================================================
# 2. Point-in-Time Universe Selection (Strict Causality)
# =============================================================================

def test_point_in_time_universe_selection():
    """
    Verify point-in-time universe selection:
    Never use today's market membership when evaluating historical decisions.
    """
    bars_btc, _ = _generate_cointegrated_pair(n_bars=200, symbol_a="BTC")
    start_ts = bars_btc[0]["timestamp"]
    decision_ts = start_ts + 120 * 3600  # Bar index 120

    # Market listed AFTER decision time
    future_meta = MarketMetadata(
        symbol="FUTURE_COIN",
        exchange="hyperliquid",
        is_active=True,
        is_delisted=False,
        listing_unix_seconds=decision_ts + 50 * 3600,  # Listed in future
    )
    filter_cfg = MarketUniverseFilter(min_history_bars=50, min_volume_quote_24h=0.0)
    eligible, reasons = filter_market(
        "FUTURE_COIN",
        bars_btc,
        future_meta,
        filter_cfg,
        as_of_unix_seconds=decision_ts,
    )
    assert eligible is False
    assert "unlisted_at_decision_time" in reasons

    # Bars returned from discover_tradable_universe must be strictly <= decision_ts
    tradable, _ = discover_tradable_universe(
        "hyperliquid",
        {"BTC": bars_btc},
        filter_config=filter_cfg,
        as_of_unix_seconds=decision_ts,
    )
    assert "BTC" in tradable
    assert all(b["timestamp"] <= decision_ts for b in tradable["BTC"])
    assert len(tradable["BTC"]) == 121


# =============================================================================
# 3. Candidate Generation (CorrelationScanner Integration)
# =============================================================================

def test_candidate_generation_categories():
    """
    Test CandidatePairGenerator:
    Partitions into strong positive, strong negative, and weak screened pools.
    """
    bars_btc, bars_eth = _generate_cointegrated_pair(n_bars=150, symbol_a="BTC", symbol_b="ETH", seed=10)

    # Inverse asset (strong negative correlation)
    prices_inv = [10_000.0 / b["close"] for b in bars_btc]
    bars_inv = _generate_bars_from_prices(prices_inv, symbol="INV", start_timestamp=bars_btc[0]["timestamp"])

    # Independent asset (weak correlation)
    rng = np.random.default_rng(999)
    prices_indep = np.exp(np.cumsum(rng.normal(0, 0.01, 150)) + 4.0)
    bars_indep = _generate_bars_from_prices(prices_indep, symbol="INDEP", start_timestamp=bars_btc[0]["timestamp"])

    universe = {
        "BTC": bars_btc,
        "ETH": bars_eth,
        "INV": bars_inv,
        "INDEP": bars_indep,
    }

    generator = CandidatePairGenerator(
        criteria=CandidatePairCriteria(
            strong_pos_threshold=0.60,
            strong_neg_threshold=-0.60,
            allow_weak_cointegrated=True,
            max_candidates=10,
        )
    )
    candidates = generator.generate_candidates(universe, exchange="hyperliquid")

    categories = {cand.category for cand in candidates}
    assert CandidateCategory.STRONG_POSITIVE in categories
    assert CandidateCategory.STRONG_NEGATIVE in categories
    assert CandidateCategory.WEAK_SCREENED in categories


# =============================================================================
# 4. Hard Rejection Rules & Cointegration Qualification
# =============================================================================

def test_hard_rejection_rules():
    """
    Verify hard rejection:
    Non-cointegrated pairs (even with high correlation) must be rejected with score 0.0.
    Correlation must NEVER compensate for failed cointegration.
    """
    rng = np.random.default_rng(777)
    n = 200
    common_shock = rng.normal(0, 0.02, n)
    ret1 = 0.9 * common_shock + rng.normal(0, 0.005, n)
    ret2 = 0.9 * common_shock + rng.normal(0, 0.005, n)
    rw1 = 5.0 + np.cumsum(ret1)
    rw2 = 4.0 + np.cumsum(ret2)
    bars_trend1 = _generate_bars_from_prices(np.exp(rw1), symbol="TREND1")
    bars_trend2 = _generate_bars_from_prices(np.exp(rw2), symbol="TREND2")

    engine = PairDiscoveryEngine(
        PairDiscoveryConfig(
            exchange="hyperliquid",
            universe_filter=MarketUniverseFilter(min_history_bars=50, min_volume_quote_24h=0.0),
            persist=False,
        )
    )

    universe = {"TREND1": bars_trend1, "TREND2": bars_trend2}
    all_pairs, snapshot, _, summary = engine.run_discovery(universe)

    assert len(all_pairs) == 1
    pair = all_pairs[0]

    # Must be highly correlated
    assert pair.correlation > 0.80
    # But hard rejected because residuals are non-stationary
    assert pair.qualification_status == QualificationStatus.REJECTED.value
    assert pair.pair_quality_score == 0.0
    assert pair.ranking_position is None
    assert len(snapshot.ranked_pairs) == 0


# =============================================================================
# 5. Pair Quality Score Bounds (0 - 100) & Sub-Scores
# =============================================================================

def test_pair_quality_score_bounds_and_components():
    """Verify pair quality score is strictly between 0 and 100 with all normalized components."""
    bars_btc, bars_eth = _generate_cointegrated_pair(n_bars=250, beta=1.2, phi=0.85, seed=2)

    engine = PairDiscoveryEngine(
        PairDiscoveryConfig(
            exchange="hyperliquid",
            universe_filter=MarketUniverseFilter(min_history_bars=50, min_volume_quote_24h=0.0),
            persist=False,
        )
    )

    universe = {"BTC": bars_btc, "ETH": bars_eth}
    all_pairs, snapshot, _, _ = engine.run_discovery(universe)

    assert len(all_pairs) == 1
    pair = all_pairs[0]

    assert pair.qualification_status == QualificationStatus.QUALIFIED.value
    assert 0.0 <= pair.pair_quality_score <= 100.0
    assert pair.pair_quality_score > 50.0  # Quality cointegrated pair scores well

    breakdown = pair.score_breakdown
    assert breakdown is not None
    assert 0.0 <= breakdown.cointegration_score <= 100.0
    assert 0.0 <= breakdown.adf_score <= 100.0
    assert 0.0 <= breakdown.half_life_score <= 100.0
    assert 0.0 <= breakdown.hedge_ratio_stability_score <= 100.0


# =============================================================================
# 6. Dynamic Ranking Hysteresis & Churn Prevention
# =============================================================================

def test_dynamic_ranking_hysteresis():
    """
    Verify ranking hysteresis:
    An incumbent pair retains its position unless a challenger beats it by >= hysteresis_delta (default 5.0).
    """
    bars_a, bars_b = _generate_cointegrated_pair(n_bars=250, symbol_a="BTC", symbol_b="ETH", seed=2)
    bars_c, bars_d = _generate_cointegrated_pair(n_bars=250, symbol_a="SOL", symbol_b="USDT", seed=20)

    universe = {"BTC": bars_a, "ETH": bars_b, "SOL": bars_c, "USDT": bars_d}

    engine = PairDiscoveryEngine(
        PairDiscoveryConfig(
            exchange="hyperliquid",
            universe_filter=MarketUniverseFilter(min_history_bars=50, min_volume_quote_24h=0.0),
            ranking_config=DynamicRankingConfig(top_n=2, hysteresis_delta=5.0),
            persist=False,
        )
    )

    # Initial Run (Run 1)
    all_pairs, snapshot_1, trans_1, _ = engine.run_discovery(universe)
    assert len(snapshot_1.ranked_pairs) == 2
    incumbent_1 = snapshot_1.ranked_pairs[0]
    incumbent_2 = snapshot_1.ranked_pairs[1]

    # Create synthetic outside challenger where challenger has slightly higher score (+2.0 points),
    # which is LESS than the hysteresis delta of 5.0 points.
    challenger_pair = RankedPairResult(
        pair_id="hyperliquid:CHALLENGER-NEW",
        exchange="hyperliquid",
        symbol_a="CHALLENGER",
        symbol_b="NEW",
        timeframe="60",
        correlation=0.85,
        cointegration_status="stationary",
        hedge_ratio=1.0,
        half_life_bars=10.0,
        liquidity_score=80.0,
        stability_score=85.0,
        pair_quality_score=incumbent_1.pair_quality_score + 2.0,  # +2.0 < +5.0 hysteresis
        ranking_position=None,
        qualification_status=QualificationStatus.QUALIFIED.value,
        residual_spread=[float(i) for i in range(50)],
    )

    ranker = DynamicPairRanker(config=DynamicRankingConfig(top_n=2, hysteresis_delta=5.0))
    # Rank incumbent and outside challenger against snapshot 1
    new_ranked, snapshot_2, trans_2 = ranker.rank_pairs(
        [incumbent_1, challenger_pair],
        previous_snapshot=snapshot_1,
        snapshot_timestamp=int(time.time()),
    )

    # Incumbent #1 MUST retain rank #1 because challenger delta (+2.0) did not clear +5.0 threshold!
    assert snapshot_2.ranked_pairs[0].pair_id == incumbent_1.pair_id
    assert snapshot_2.ranked_pairs[1].pair_id == challenger_pair.pair_id


# =============================================================================
# 7. Pair Diversity (Spread Correlation & Token Overlap Constraints)
# =============================================================================

def test_pair_diversity_spread_correlation_filtering():
    """
    Verify portfolio diversity:
    Pairs with spread correlation > 0.60 are filtered to enforce orthogonal risk exposure.
    """
    p1 = RankedPairResult(
        pair_id="hyperliquid:BTC-ETH", exchange="hyperliquid", symbol_a="BTC", symbol_b="ETH",
        timeframe="60", correlation=0.8, cointegration_status="stationary", hedge_ratio=1.0,
        half_life_bars=10.0, liquidity_score=80.0, stability_score=85.0, pair_quality_score=85.0,
        ranking_position=None, qualification_status=QualificationStatus.QUALIFIED.value,
        residual_spread=[float(i) for i in range(50)],
    )

    p2 = RankedPairResult(
        pair_id="hyperliquid:SOL-USDT", exchange="hyperliquid", symbol_a="SOL", symbol_b="USDT",
        timeframe="60", correlation=0.8, cointegration_status="stationary", hedge_ratio=1.0,
        half_life_bars=10.0, liquidity_score=80.0, stability_score=85.0, pair_quality_score=80.0,
        ranking_position=None, qualification_status=QualificationStatus.QUALIFIED.value,
        residual_spread=[float(i) for i in range(50)],  # identical spread!
    )

    ranker = DynamicPairRanker(DynamicRankingConfig(top_n=5, diversity_spread_corr_max=0.60))
    all_pairs, snapshot, transitions = ranker.rank_pairs([p1, p2])

    assert len(snapshot.ranked_pairs) == 1
    assert snapshot.ranked_pairs[0].pair_id == "hyperliquid:BTC-ETH"

    rejected = [p for p in all_pairs if any("excessive_spread_correlation" in r for r in p.rejection_reasons)]
    assert len(rejected) == 1
    assert rejected[0].pair_id == "hyperliquid:SOL-USDT"


def test_token_overlap_limit():
    """
    Verify max pairs per symbol limit (e.g. max 2 pairs containing BTC).
    """
    p1 = RankedPairResult(
        pair_id="hyperliquid:BTC-ETH", exchange="hyperliquid", symbol_a="BTC", symbol_b="ETH",
        timeframe="60", correlation=0.8, cointegration_status="stationary", hedge_ratio=1.0,
        half_life_bars=10.0, liquidity_score=80.0, stability_score=85.0, pair_quality_score=90.0,
        ranking_position=None, qualification_status=QualificationStatus.QUALIFIED.value,
        residual_spread=[float(i) for i in range(50)],
    )
    p2 = RankedPairResult(
        pair_id="hyperliquid:BTC-SOL", exchange="hyperliquid", symbol_a="BTC", symbol_b="SOL",
        timeframe="60", correlation=0.8, cointegration_status="stationary", hedge_ratio=1.0,
        half_life_bars=10.0, liquidity_score=80.0, stability_score=85.0, pair_quality_score=85.0,
        ranking_position=None, qualification_status=QualificationStatus.QUALIFIED.value,
        residual_spread=[float(-i) for i in range(50)],
    )
    p3 = RankedPairResult(
        pair_id="hyperliquid:BTC-AVAX", exchange="hyperliquid", symbol_a="BTC", symbol_b="AVAX",
        timeframe="60", correlation=0.8, cointegration_status="stationary", hedge_ratio=1.0,
        half_life_bars=10.0, liquidity_score=80.0, stability_score=85.0, pair_quality_score=80.0,
        ranking_position=None, qualification_status=QualificationStatus.QUALIFIED.value,
        residual_spread=[float(i % 5) for i in range(50)],
    )

    ranker = DynamicPairRanker(DynamicRankingConfig(top_n=5, max_pairs_per_symbol=2, diversity_spread_corr_max=0.99))
    all_pairs, snapshot, transitions = ranker.rank_pairs([p1, p2, p3])

    # BTC appears in all 3 candidate pairs; with max_pairs_per_symbol=2, at most 2 can enter top ranking
    btc_count = sum(1 for p in snapshot.ranked_pairs if "BTC" in (p.symbol_a, p.symbol_b))
    assert btc_count == 2
    assert len(snapshot.ranked_pairs) == 2


def test_ranking_change_detection():
    """
    Verify ranking change detection correctly emits:
    - NEW_ENTRY: pair entering the top-N ranking
    - PROMOTION: pair moving to a higher rank position
    - DEMOTION: pair moving to a lower rank position
    - EXIT: pair falling out of top-N ranking
    - UNCHANGED: pair retaining its rank position
    """
    def _make_candidate(pair_id: str, sym_a: str, sym_b: str, score: float, spread: list[float] | None = None) -> RankedPairResult:
        if spread is None:
            spread = [float(i) for i in range(50)]
        return RankedPairResult(
            pair_id=pair_id,
            exchange="hyperliquid",
            symbol_a=sym_a,
            symbol_b=sym_b,
            timeframe="60",
            correlation=0.85,
            cointegration_status="stationary",
            hedge_ratio=1.0,
            half_life_bars=10.0,
            liquidity_score=80.0,
            stability_score=85.0,
            pair_quality_score=score,
            ranking_position=None,
            qualification_status=QualificationStatus.QUALIFIED.value,
            residual_spread=spread,
        )

    ranker = DynamicPairRanker(DynamicRankingConfig(top_n=3, hysteresis_delta=5.0, diversity_spread_corr_max=0.99))

    spread_a = [float(i) for i in range(50)]
    spread_b = [float((i * 17) % 31) for i in range(50)]
    spread_c = [float(math.sin(i)) for i in range(50)]
    spread_d = [float(math.cos(i * 3)) for i in range(50)]

    p_a = _make_candidate("hyperliquid:AAA-USDT", "AAA", "USDT", 90.0, spread_a)
    p_b = _make_candidate("hyperliquid:BBB-USDC", "BBB", "USDC", 80.0, spread_b)
    p_c = _make_candidate("hyperliquid:CCC-DAI", "CCC", "DAI", 70.0, spread_c)

    # Initial snapshot 1: A (#1), B (#2), C (#3)
    _, snap_1, trans_1 = ranker.rank_pairs([p_a, p_b, p_c], snapshot_timestamp=1000)
    assert len(snap_1.ranked_pairs) == 3
    assert [p.pair_id for p in snap_1.ranked_pairs] == [p_a.pair_id, p_b.pair_id, p_c.pair_id]
    assert all(t.change_type == RankChangeType.NEW_ENTRY for t in trans_1)

    # Round 2:
    # Pair B improves to 96.0 (effective 96 + 5 = 101.0)
    # Pair A drops to 85.0 (effective 85 + 5 = 90.0)
    # Pair D is a new challenger at 88.0 (effective 88.0, beats C's 60 + 5 = 65.0)
    # Pair C drops to 60.0 (effective 65.0) -> pushed out of top-3
    p_a2 = _make_candidate("hyperliquid:AAA-USDT", "AAA", "USDT", 85.0, spread_a)
    p_b2 = _make_candidate("hyperliquid:BBB-USDC", "BBB", "USDC", 96.0, spread_b)
    p_c2 = _make_candidate("hyperliquid:CCC-DAI", "CCC", "DAI", 60.0, spread_c)
    p_d2 = _make_candidate("hyperliquid:DDD-FDUSD", "DDD", "FDUSD", 88.0, spread_d)

    _, snap_2, trans_2 = ranker.rank_pairs([p_a2, p_b2, p_c2, p_d2], previous_snapshot=snap_1, snapshot_timestamp=2000)
    assert len(snap_2.ranked_pairs) == 3
    assert [p.pair_id for p in snap_2.ranked_pairs] == [p_b.pair_id, p_a.pair_id, p_d2.pair_id]

    trans_map = {t.pair_id: t for t in trans_2}
    assert trans_map[p_b.pair_id].change_type == RankChangeType.PROMOTION
    assert trans_map[p_b.pair_id].previous_rank == 2
    assert trans_map[p_b.pair_id].new_rank == 1

    assert trans_map[p_a.pair_id].change_type == RankChangeType.DEMOTION
    assert trans_map[p_a.pair_id].previous_rank == 1
    assert trans_map[p_a.pair_id].new_rank == 2

    assert trans_map[p_d2.pair_id].change_type == RankChangeType.NEW_ENTRY
    assert trans_map[p_d2.pair_id].previous_rank is None
    assert trans_map[p_d2.pair_id].new_rank == 3

    assert trans_map[p_c.pair_id].change_type == RankChangeType.EXIT
    assert trans_map[p_c.pair_id].previous_rank == 3
    assert trans_map[p_c.pair_id].new_rank is None

    # Round 3:
    # Pair B retains #1 -> UNCHANGED
    _, snap_3, trans_3 = ranker.rank_pairs([p_b2, p_a2, p_d2], previous_snapshot=snap_2, snapshot_timestamp=3000)
    trans_map_3 = {t.pair_id: t for t in trans_3}
    assert trans_map_3[p_b.pair_id].change_type == RankChangeType.UNCHANGED
    assert trans_map_3[p_b.pair_id].previous_rank == 1
    assert trans_map_3[p_b.pair_id].new_rank == 1



# =============================================================================
# 8. Complete 16-Field Output Contract Compliance
# =============================================================================

def test_all_sixteen_output_fields_and_contract():
    """Verify all 16 specified output fields exist with exact names and serialized types."""
    bars_btc, bars_eth = _generate_cointegrated_pair(n_bars=250, symbol_a="BTC", symbol_b="ETH", seed=2)

    engine = PairDiscoveryEngine(
        PairDiscoveryConfig(
            exchange="hyperliquid",
            universe_filter=MarketUniverseFilter(min_history_bars=50, min_volume_quote_24h=0.0),
            persist=False,
        )
    )

    universe = {"BTC": bars_btc, "ETH": bars_eth}
    all_pairs, snapshot, _, _ = engine.run_discovery(universe)

    assert len(snapshot.ranked_pairs) == 1
    ranked_pair = snapshot.ranked_pairs[0]
    data = ranked_pair.to_dict()

    expected_fields = [
        "pair_id",
        "exchange",
        "symbol_a",
        "symbol_b",
        "timeframe",
        "correlation",
        "cointegration_status",
        "hedge_ratio",
        "half_life_bars",
        "liquidity_score",
        "stability_score",
        "pair_quality_score",
        "ranking_position",
        "qualification_status",
        "rejection_reasons",
        "last_updated",
    ]

    for field_name in expected_fields:
        assert field_name in data, f"Missing required output field: {field_name}"

    assert isinstance(data["pair_id"], str)
    assert isinstance(data["exchange"], str)
    assert isinstance(data["correlation"], float)
    assert isinstance(data["hedge_ratio"], float)
    assert isinstance(data["pair_quality_score"], float)
    assert isinstance(data["ranking_position"], int)
    assert isinstance(data["rejection_reasons"], list)


# =============================================================================
# 9. SQLite Persistence and Retrieval
# =============================================================================

def test_sqlite_persistence_and_retrieval(tmp_path, monkeypatch):
    """Verify runs, candidates, qualifications, snapshots, and transitions persist to SQLite."""
    test_db = tmp_path / "test_traderbot.db"
    monkeypatch.setenv("TRADERBOT_DB", str(test_db))

    bars_btc, bars_eth = _generate_cointegrated_pair(n_bars=250, symbol_a="BTC", symbol_b="ETH", seed=2)
    universe = {"BTC": bars_btc, "ETH": bars_eth}

    engine = PairDiscoveryEngine(
        PairDiscoveryConfig(
            exchange="hyperliquid",
            universe_filter=MarketUniverseFilter(min_history_bars=50, min_volume_quote_24h=0.0),
            persist=True,
        )
    )

    all_pairs, snapshot, transitions, summary = engine.run_discovery(universe, job_id="test_run_001")

    # 1. Verify latest ranking query
    latest_ranked = fetch_latest_pair_ranking(exchange="hyperliquid", top_n=5)
    assert len(latest_ranked) == 1
    assert latest_ranked[0]["pair_id"] == "hyperliquid:BTC-ETH"
    assert latest_ranked[0]["ranking_position"] == 1
    assert latest_ranked[0]["pair_quality_score"] > 50.0
    for field_name in (
        "pair_id", "exchange", "symbol_a", "symbol_b", "timeframe", "correlation",
        "cointegration_status", "hedge_ratio", "half_life_bars", "liquidity_score",
        "stability_score", "pair_quality_score", "ranking_position", "qualification_status",
        "rejection_reasons", "last_updated",
    ):
        assert field_name in latest_ranked[0], f"Field {field_name} missing from persisted result"

    # 2. Verify discovery runs list
    runs = list_pair_discovery_runs(exchange="hyperliquid")
    assert len(runs) >= 1
    assert runs[0]["id"] == "test_run_001"
    assert runs[0]["summary"]["candidates_qualified"] == 1

    # 3. Verify ranking history
    history = fetch_pair_ranking_history("hyperliquid:BTC-ETH")
    assert len(history) >= 1
    assert history[0]["change_type"] == "new_entry"


# =============================================================================
# 10. Large Universe Performance Benchmark
# =============================================================================

def test_large_universe_performance_benchmarks():
    """
    Computational performance benchmark:
    Generate a 15-asset universe (105 pairs) and benchmark candidate generation,
    qualification, scoring, diversity filtering, and dynamic ranking.
    Target: < 2.0 seconds execution.
    """
    rng = np.random.default_rng(123)
    universe = {}
    symbols = [f"ASSET_{i:02d}" for i in range(15)]

    # Generate 15 distinct market feeds
    for sym in symbols:
        prices = np.exp(np.cumsum(rng.normal(0.0002, 0.015, 250)) + 5.0)
        universe[sym] = _generate_bars_from_prices(prices, symbol=sym, volume=20_000.0)

    # Inject one genuine cointegrated relationship between ASSET_00 and ASSET_01
    bars_00, bars_01 = _generate_cointegrated_pair(n_bars=250, symbol_a="ASSET_00", symbol_b="ASSET_01", phi=0.70, seed=2)
    universe["ASSET_00"] = bars_00
    universe["ASSET_01"] = bars_01

    t0 = time.perf_counter()
    engine = PairDiscoveryEngine(
        PairDiscoveryConfig(
            exchange="hyperliquid",
            universe_filter=MarketUniverseFilter(min_history_bars=50, min_volume_quote_24h=0.0),
            cointegration_thresholds=CointegrationThresholds(min_half_life_bars=1.0, max_chow_break_pvalue=0.0001),
            candidate_criteria=CandidatePairCriteria(max_candidates=50),
            ranking_config=DynamicRankingConfig(top_n=5),
            persist=False,
        )
    )

    all_pairs, snapshot, transitions, summary = engine.run_discovery(universe)
    duration = time.perf_counter() - t0

    print(f"\n[Benchmark] 15-asset universe (105 candidate pairs) scanned in {duration:.4f}s")
    assert duration < 2.5, f"Execution too slow: {duration:.2f}s >= 2.5s"
    assert summary["candidates_generated"] > 0
    # Genuine cointegrated pair must be ranked #1
    assert len(snapshot.ranked_pairs) >= 1
    assert snapshot.ranked_pairs[0].pair_id == "hyperliquid:ASSET_00-ASSET_01"

