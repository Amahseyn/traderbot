from traderbot.algorithms.strategies.example import SmaCrossAlgorithm
from traderbot.backtesting import load_bars_csv, normalize_bar, run_backtest
from traderbot.bots.base import Bot
from traderbot.nobitex.client import NobitexClient
from traderbot.data.export import write_csv
from traderbot.traders.execution import ExecutionPolicy
from traderbot.traders.position import order_action_for_long_only
from traderbot.traders.strategies.algorithm_trader import AlgorithmTrader


def _bars(closes: list[float]) -> list[dict]:
    return [
        {
            "symbol": "BTCIRT",
            "resolution": "D",
            "timestamp": i,
            "datetime_utc": "",
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "volume": 1.0,
        }
        for i, c in enumerate(closes)
    ]


def test_sma_cross_signals():
    algo = SmaCrossAlgorithm(fast=2, slow=3)
    bars = _bars([1, 2, 3, 2, 1])
    assert algo.on_bar(bars[0]) == "hold"
    assert algo.on_bar(bars[1]) == "hold"
    assert algo.on_bar(bars[2]) == "hold"
    algo.reset()
    for bar in bars[:4]:
        algo.on_bar(bar)
    assert algo.on_bar(bars[4]) == "sell"


def test_run_backtest_long_only():
    # flat, then up trend triggers buy; later down triggers sell
    closes = [10.0] * 5 + [11.0, 12.0, 13.0, 12.0, 11.0, 10.0, 9.0]
    result = run_backtest(SmaCrossAlgorithm(fast=2, slow=3), _bars(closes), initial_cash=1000.0)
    assert len(result.trades) == 2
    assert result.trades[0].action == "buy"
    assert result.trades[1].action == "sell"
    assert max(eq for _, eq in result.equity_curve) > result.initial_cash
    assert len(result.equity_curve) == len(closes)


def test_csv_roundtrip(tmp_path):
    path = tmp_path / "btc.csv"
    rows = _bars([1.0, 2.0, 3.0])
    write_csv(path, rows)
    loaded = load_bars_csv(path)
    assert len(loaded) == 3
    assert loaded[0]["close"] == 1.0
    assert isinstance(normalize_bar(loaded[1])["close"], float)


def test_long_only_gates_repeat_buys():
    assert order_action_for_long_only(False, "buy") == "buy"
    assert order_action_for_long_only(True, "buy") is None
    assert order_action_for_long_only(True, "sell") == "sell"
    assert order_action_for_long_only(False, "sell") is None


def test_algorithm_trader_calls_on_signal(keys):
    from traderbot.algorithms.base import Algorithm, Bar, SignalAction

    class _BuyAlgo(Algorithm):
        def on_bar(self, bar: Bar) -> SignalAction:
            return "buy"

    pub, priv = keys
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    bar = _bars([5.0])[0]
    signals: list[str] = []

    class T(AlgorithmTrader):
        def on_signal(self, action, _bar):
            signals.append(action)

    t = T(client, _BuyAlgo(), bar_source=lambda: bar, execution=ExecutionPolicy.live())
    t.step()
    assert signals == ["buy"]


def test_algorithm_trader_with_bot(keys):
    pub, priv = keys
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    algo = SmaCrossAlgorithm(fast=2, slow=3)
    bar = _bars([1, 2, 3, 4, 5])[4]
    t = AlgorithmTrader(client, algo, bar_source=lambda: bar)
    Bot([t]).run_once()
    assert t.algorithm is algo
