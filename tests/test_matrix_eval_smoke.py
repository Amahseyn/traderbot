from traderbot.backtesting.matrix_eval import MatrixEvalConfig, evaluate_single_asset_cell
import random


def _bars(count: int, start_price: float = 100.0) -> list[dict]:
    return [
        {
            "symbol": "BTCUSDT",
            "resolution": "60",
            "timestamp": index * 3600,
            "open": start_price,
            "high": start_price * (1.02 if index % 2 == 0 else 1.01),
            "low": start_price * (0.98 if index % 2 == 0 else 0.99),
            "close": start_price * (1.01 if index % 3 == 0 else 0.99),
            "volume": 1.0,
        }
        for index in range(count)
    ]


def test_evaluate_single_asset_cell_smoke():
    bars = _bars(800)
    config = MatrixEvalConfig(sample_count=5, use_cache=False)
    samples = evaluate_single_asset_cell(
        exchange="hyperliquid",
        strategy_id="sma_cross",
        symbol_key="btc",
        resolution="60",
        bars=bars,
        config=config,
        rng=random.Random(1),
    )
    assert len(samples) >= 1
    assert "return_pct" in samples[0]
