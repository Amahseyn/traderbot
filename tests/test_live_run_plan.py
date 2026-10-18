from lab.live_run_plan import (
    MAX_LIVE_BATCH_COMBOS,
    assert_unique_live_run_combos,
    build_live_run_combos,
    combo_unique_key,
    market_combos_for_live_run,
    resolved_horizons_for_live_run,
    strategy_ids_for_live_run,
)


def test_resolved_horizons_defaults():
    assert resolved_horizons_for_live_run([]) == ["60"]


def test_single_market_single_strategy():
    combos = build_live_run_combos(
        multi_run=False,
        src="btc",
        dst="usdt",
        market_symbol="BTCUSDT",
        batch_markets=[],
        horizons=["60"],
        multi_strategy=False,
        strategy_id="sma_cross",
        batch_strategy_ids=[],
    )
    assert len(combos) == 1
    assert combos[0].strategy_id == "sma_cross"
    assert combos[0].symbol == "BTCUSDT"
    assert combos[0].interval == "60"


def test_single_market_multiple_horizons():
    combos = build_live_run_combos(
        multi_run=False,
        src="btc",
        dst="usdt",
        market_symbol="BTCUSDT",
        batch_markets=[],
        horizons=["1", "60"],
        multi_strategy=False,
        strategy_id="sma_cross",
        batch_strategy_ids=[],
    )
    assert len(combos) == 2
    assert {row.interval for row in combos} == {"1", "60"}


def test_multi_market_multi_interval():
    markets = market_combos_for_live_run(
        multi_run=True,
        src="btc",
        dst="usdt",
        market_symbol="BTCUSDT",
        batch_markets=[
            {"src": "btc", "dst": "usdt", "symbol": "BTCUSDT"},
            {"src": "eth", "dst": "usdt", "symbol": "ETHUSDT"},
        ],
        horizons=["1", "60"],
    )
    assert len(markets) == 4


def test_multi_strategy_cartesian():
    combos = build_live_run_combos(
        multi_run=False,
        src="btc",
        dst="usdt",
        market_symbol="BTCUSDT",
        batch_markets=[],
        horizons=["5"],
        multi_strategy=True,
        strategy_id="sma_cross",
        batch_strategy_ids=["sma_cross", "rsi_threshold", "sma_cross"],
    )
    assert len(combos) == 2
    assert {row.strategy_id for row in combos} == {"sma_cross", "rsi_threshold"}


def test_full_batch_markets_intervals_strategies():
    combos = build_live_run_combos(
        multi_run=True,
        src="btc",
        dst="usdt",
        market_symbol="BTCUSDT",
        batch_markets=[
            {"src": "btc", "dst": "usdt", "symbol": "BTCUSDT"},
            {"src": "eth", "dst": "usdt", "symbol": "ETHUSDT"},
        ],
        horizons=["1"],
        multi_strategy=True,
        strategy_id="sma_cross",
        batch_strategy_ids=["sma_cross", "rsi_threshold"],
    )
    assert len(combos) == 4
    assert MAX_LIVE_BATCH_COMBOS == 16


def test_full_2x2x2_cartesian_is_unique():
    combos = build_live_run_combos(
        multi_run=True,
        src="btc",
        dst="usdt",
        market_symbol="BTCUSDT",
        batch_markets=[
            {"src": "btc", "dst": "usdt", "symbol": "BTCUSDT"},
            {"src": "eth", "dst": "usdt", "symbol": "ETHUSDT"},
        ],
        horizons=["1", "60"],
        multi_strategy=True,
        strategy_id="sma_cross",
        batch_strategy_ids=["sma_cross", "rsi_threshold"],
    )
    assert len(combos) == 8
    assert_unique_live_run_combos(combos)
    keys = {combo_unique_key(row) for row in combos}
    assert len(keys) == 8
    assert ("BTCUSDT", "1", "sma_cross") in {
        (row.symbol, row.interval, row.strategy_id) for row in combos
    }
    assert ("ETHUSDT", "60", "rsi_threshold") in {
        (row.symbol, row.interval, row.strategy_id) for row in combos
    }


def test_strategy_ids_dedupes():
    ids = strategy_ids_for_live_run(
        multi_strategy=True,
        strategy_id="ignored",
        batch_strategy_ids=["a", "b", "a"],
    )
    assert ids == ["a", "b"]
