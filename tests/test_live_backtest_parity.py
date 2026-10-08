from __future__ import annotations

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.algorithms.warmup import warmup_bar_count
from traderbot.backtesting.engine import normalize_bar, run_backtest


def _bars(closes: list[float]) -> list[dict]:
    return [
        normalize_bar(
            {
                "timestamp": index,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
            },
        )
        for index, close in enumerate(closes)
    ]


def _backtest_signals(strategy_id: str, kwargs: dict, bars: list[dict]) -> list[str]:
    algorithm = algorithm_for_id(strategy_id, **kwargs)
    signals: list[str] = []
    for bar in bars:
        signals.append(algorithm.on_bar(bar))
    return signals


def _live_tail_signals(strategy_id: str, kwargs: dict, bars: list[dict]) -> list[str]:
    warmup_count = warmup_bar_count(strategy_id, kwargs)
    algorithm = algorithm_for_id(strategy_id, **kwargs)
    tail: list[str] = []
    for bar_index, bar in enumerate(bars):
        signal = algorithm.on_bar(bar)
        if bar_index >= warmup_count:
            tail.append(signal)
    return tail


def test_live_warmup_matches_backtest_signals():
    closes = [100 + index * 0.3 + (index % 5) for index in range(120)]
    bars = _bars(closes)
    cases = [
        ("sma_cross", {"fast": 5, "slow": 20}),
        ("ema_cross", {"fast": 12, "slow": 26}),
        ("rsi_threshold", {"period": 14}),
        ("macd_cross", {"fast": 12, "slow": 26, "signal": 9}),
    ]
    for strategy_id, kwargs in cases:
        backtest = _backtest_signals(strategy_id, kwargs, bars)
        warmup_count = warmup_bar_count(strategy_id, kwargs)
        live_tail = _live_tail_signals(strategy_id, kwargs, bars)
        assert live_tail == backtest[warmup_count:]
        run_backtest(algorithm_for_id(strategy_id, **kwargs), bars)
