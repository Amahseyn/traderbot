from pathlib import Path

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.algorithms.strategies.pair_trading import PairTradingSpreadAlgorithm
from traderbot.backtesting import run_backtest
from traderbot.backtesting.pair_research import run_pair_backtest_preview
from traderbot.utils.pair_bars import align_bars_by_timestamp


def _bar(timestamp: int, close: float, hedge_close: float | None = None) -> dict:
    payload = {
        "symbol": "ETHIRT",
        "resolution": "60",
        "timestamp": timestamp,
        "datetime_utc": "",
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
    }
    if hedge_close is not None:
        payload["hedge_close"] = hedge_close
    return payload


def _cointegrated_series(bar_count: int, *, noise: float = 0.002) -> tuple[list[dict], list[dict]]:
    primary: list[dict] = []
    hedge: list[dict] = []
    hedge_price = 100.0
    spread_shock = 0.0
    for index in range(bar_count):
        hedge_price *= 1.0 + 0.001 * (index % 5 - 2) * 0.1
        spread_shock = 0.9 * spread_shock + noise * (1 if index % 17 == 0 else -1 if index % 23 == 0 else 0)
        primary_price = hedge_price * (1.05 + spread_shock)
        timestamp = index * 3600
        primary.append(_bar(timestamp, primary_price))
        hedge.append(_bar(timestamp, hedge_price))
    return primary, hedge


def test_pair_trading_requires_hedge_close():
    algo = PairTradingSpreadAlgorithm(lookback=5, hedge_lookback=5, entry_z=1.0, exit_z=0.0)
    assert algo.on_bar(_bar(0, 100.0)) == "hold"


def test_pair_trading_emits_buy_on_wide_negative_spread():
    primary, hedge = _cointegrated_series(80, noise=0.02)
    aligned = align_bars_by_timestamp(primary, hedge)
    algo = PairTradingSpreadAlgorithm(lookback=10, hedge_lookback=10, entry_z=1.2, exit_z=0.2)
    actions = [algo.on_bar(bar) for bar in aligned]
    assert "buy" in actions


def test_pair_backtest_preview_runs(tmp_path: Path):
    primary, hedge = _cointegrated_series(120)
    primary_path = tmp_path / "eth.csv"
    hedge_path = tmp_path / "btc.csv"
    _write_csv(primary_path, primary)
    _write_csv(hedge_path, hedge)
    payload = run_pair_backtest_preview(
        primary_csv=primary_path,
        hedge_csv=hedge_path,
        strategy_namespace=None,
    )
    assert payload["summary"]["return_pct"] is not None
    assert len(payload["equity_curve"]) == len(primary)
    assert len(payload["series"]["z_score"]) == len(primary)


def test_pair_trading_backtest_with_fees():
    primary, hedge = _cointegrated_series(100, noise=0.015)
    aligned = align_bars_by_timestamp(primary, hedge)
    algo = algorithm_for_id("pair_trading", lookback=15, hedge_lookback=15, entry_z=1.5, exit_z=0.3)
    result = run_backtest(algo, aligned, initial_cash=10_000.0, fee_rate=0.002)
    assert result.final_equity > 0
    assert len(result.trades) >= 1


def _write_csv(path: Path, bars: list[dict]) -> None:
    header = "symbol,resolution,timestamp,datetime_utc,open,high,low,close,volume\n"
    lines = [
        f"{bar['symbol']},{bar['resolution']},{bar['timestamp']},,{bar['open']},{bar['high']},{bar['low']},{bar['close']},{bar['volume']}"
        for bar in bars
    ]
    path.write_text(header + "\n".join(lines), encoding="utf-8")
