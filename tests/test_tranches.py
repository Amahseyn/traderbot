"""Tranche re-entry: repeated entry signals add tranches of the same position.

``max_tranches=1`` (default, with ``target_exposure=1.0``) keeps legacy single-position
behavior everywhere. With ``max_tranches > 1`` a fresh entry signal may add the next
tranche after ``tranche_gap_bars`` bars; each new tranche targets ``tranches x
target_exposure`` equity. Sells still exit flat.
"""

import pytest

from traderbot.algorithms.registry import algorithm_for_id, strategy_kwargs_from_namespace
from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.backtesting import run_backtest

TRANCHE_STRATEGY_IDS = (
    "rsi_threshold",
    "bollinger_mean_reversion",
    "breakout_atr",
    "rsi_trend",
    "rsi_divergence",
    "chart_patterns",
    "momentum_shock",
    "online_logistic",
)


def _series(closes) -> list[dict]:
    bars = []
    previous = closes[0]
    for index, close in enumerate(closes):
        bars.append({
            "timestamp": index + 1,
            "open": previous,
            "high": max(close, previous),
            "low": min(close, previous),
            "close": close,
            "volume": 1.0,
        })
        previous = close
    return bars


def _signal_sizes(algorithm, bars) -> list[tuple[str, float | None]]:
    pairs = []
    for bar in bars:
        action = algorithm.on_bar(bar)
        size = algorithm.order_size() if action != "hold" else None
        exposure = None if size is None else float(size.target_exposure)
        pairs.append((action, exposure))
    return pairs


# --- registry / CLI wiring -------------------------------------------------------------------


@pytest.mark.parametrize("strategy_id", TRANCHE_STRATEGY_IDS)
def test_namespace_wires_tranche_params(strategy_id: str) -> None:
    namespace = default_strategy_namespace(max_tranches=3, tranche_gap_bars=2)
    kwargs = strategy_kwargs_from_namespace(strategy_id, namespace)
    assert kwargs["max_tranches"] == 3
    assert kwargs["tranche_gap_bars"] == 2


@pytest.mark.parametrize("strategy_id", TRANCHE_STRATEGY_IDS)
def test_accepts_tranche_kwargs(strategy_id: str) -> None:
    algorithm = algorithm_for_id(strategy_id, target_exposure=0.25, max_tranches=3)
    assert algorithm.order_size() is None
    with pytest.raises(ValueError):
        algorithm_for_id(strategy_id, target_exposure=0.25, max_tranches=5)  # 5 * 0.25 > 1
    with pytest.raises(ValueError):
        algorithm_for_id(strategy_id, max_tranches=0)


# --- rsi_threshold (continuous-fire threshold family) -----------------------------------------


def test_rsi_threshold_stacks_tranches():
    # Flat closes keep RSI at 50 <= oversold(55): a fresh buy fires every bar.
    algorithm = algorithm_for_id(
        "rsi_threshold", period=2, oversold=55.0, overbought=60.0,
        target_exposure=0.25, max_tranches=3,
    )
    pairs = _signal_sizes(algorithm, _series([10.0] * 8))
    assert [pair for pair in pairs if pair[0] != "hold"] == [
        ("buy", 0.25), ("buy", 0.5), ("buy", 0.75), ("buy", 0.75), ("buy", 0.75), ("buy", 0.75),
    ]


def test_rsi_threshold_tranche_gap_spacing():
    # Gap 2: entry tranches accepted every 3rd bar; blocked signals re-emit a no-op
    # buy at the current filled level instead of stacking early.
    algorithm = algorithm_for_id(
        "rsi_threshold", period=2, oversold=55.0, overbought=60.0,
        target_exposure=0.25, max_tranches=3, tranche_gap_bars=2,
    )
    pairs = _signal_sizes(algorithm, _series([10.0] * 8))
    accepted: list[tuple[str, float]] = []
    for action, exposure in pairs:
        if action == "buy" and (not accepted or exposure > accepted[-1][1]):
            accepted.append((action, exposure))
    assert accepted == [("buy", 0.25), ("buy", 0.5), ("buy", 0.75)]


def test_rsi_threshold_tranches_reset_on_exit():
    # Gap 100 keeps every phase to a single tranche; the sell must reset the
    # counter so the next entry starts at tranche 1 again (0.25, not 0.5).
    algorithm = algorithm_for_id(
        "rsi_threshold", period=2, oversold=55.0, overbought=60.0,
        target_exposure=0.25, max_tranches=2, tranche_gap_bars=100,
    )
    pairs = _signal_sizes(algorithm, _series([10.0, 9.5, 9.5, 10.0, 10.5, 10.5, 9.5]))
    first_buy = next(exposure for action, exposure in pairs if action == "buy")
    assert first_buy == 0.25
    sell_index = next(index for index, (action, _) in enumerate(pairs) if action == "sell")
    reset_buys = [exposure for action, exposure in pairs[sell_index:] if action == "buy"]
    assert reset_buys == [0.25]


def test_rsi_threshold_default_stays_legacy():
    algorithm = algorithm_for_id("rsi_threshold", period=2, oversold=55.0, overbought=60.0)
    pairs = _signal_sizes(algorithm, _series([10.0] * 8))
    buys = [exposure for action, exposure in pairs if action == "buy"]
    assert buys
    assert all(exposure is None for exposure in buys)


# --- bollinger --------------------------------------------------------------------------------


def test_bollinger_stacks_tranches():
    algorithm = algorithm_for_id(
        "bollinger_mean_reversion", period=3, num_std=0.5,
        target_exposure=0.25, max_tranches=3,
    )
    pairs = _signal_sizes(algorithm, _series([100.0] * 7))
    exposures = [exposure for action, exposure in pairs if action == "buy"]
    assert exposures == [0.25, 0.5, 0.75, 0.75, 0.75]


# --- breakout_atr ------------------------------------------------------------------------------


def test_breakout_atr_adds_tranche_after_gap():
    algorithm = algorithm_for_id(
        "breakout_atr", lookback_bars=4, atr_period=2, atr_multiplier=0.1,
        stop_atr_multiplier=0.2, target_exposure=0.25, max_tranches=2, tranche_gap_bars=3,
    )
    bars = _series([100.0] * 5 + [100.5, 100.7, 100.8, 101.0, 101.0])
    pairs = _signal_sizes(algorithm, bars)
    actions_with_size = [pair for pair in pairs if pair[0] != "hold"]
    assert actions_with_size[0] == ("buy", 0.25)
    assert ("buy", 0.5) in actions_with_size


def test_breakout_atr_default_single_position():
    algorithm = algorithm_for_id(
        "breakout_atr", lookback_bars=4, atr_period=2, atr_multiplier=0.1, stop_atr_multiplier=0.2,
    )
    bars = _series([100.0] * 5 + [100.5, 100.7, 100.8, 101.0, 101.0])
    pairs = _signal_sizes(algorithm, bars)
    assert [pair for pair in pairs if pair[0] != "hold"] == [("buy", None)]


# --- momentum_shock -----------------------------------------------------------------------------


def test_momentum_shock_adds_tranches():
    class SequentialSource:
        def __init__(self) -> None:
            self.scores = [0.0, 0.0, 1.0, 1.0, 0.0, 1.0, -1.0]
            self.index = 0

        def reset(self) -> None:
            self.index = 0

        def score_bar(self, bar: dict) -> float:
            score = self.scores[min(self.index, len(self.scores) - 1)]
            self.index += 1
            return score

    algorithm = algorithm_for_id(
        "momentum_shock", shock_hold_bars=6, event_source=SequentialSource(),
        target_exposure=0.25, max_tranches=2,
    )
    pairs = _signal_sizes(algorithm, _series([100.0] * 8))
    assert [pair for pair in pairs if pair[0] != "hold"] == [
        ("buy", 0.25), ("buy", 0.5), ("sell", 0.0),
    ]


# --- online_logistic -----------------------------------------------------------------------------


def test_online_logistic_adds_tranches():
    algorithm = algorithm_for_id(
        "online_logistic", lookback_bars=24, ml_horizon_bars=1, ml_warmup_samples=1,
        ml_buy_threshold=0.4, ml_sell_threshold=0.25,
        target_exposure=0.25, max_tranches=2,
    )
    pairs = _signal_sizes(algorithm, _series([100.0] * 30))
    buys = [exposure for action, exposure in pairs if action == "buy"]
    assert buys == [0.25, 0.5]


# --- stateful strategies: params accepted, legacy unchanged --------------------------------


@pytest.mark.parametrize("strategy_id", ("rsi_trend", "rsi_divergence", "chart_patterns"))
def test_stateful_strategies_accept_tranche_params(strategy_id: str) -> None:
    algorithm = algorithm_for_id(strategy_id, target_exposure=0.25, max_tranches=2)
    assert algorithm.order_size() is None


# --- engine integration --------------------------------------------------------------------------


def test_engine_accumulates_tranches_and_exits_flat():
    algorithm = algorithm_for_id(
        "breakout_atr", lookback_bars=4, atr_period=2, atr_multiplier=0.1,
        stop_atr_multiplier=0.2, target_exposure=0.25, max_tranches=2, tranche_gap_bars=3,
    )
    bars = _series([100.0] * 5 + [100.5, 100.7, 100.8, 101.0, 96.0, 95.0])
    result = run_backtest(algorithm, bars, initial_cash=1000.0, fee_rate=0.0)
    buys = [trade for trade in result.trades if trade.action == "buy"]
    sells = [trade for trade in result.trades if trade.action == "sell"]
    assert len(buys) == 2
    assert buys[0].size * buys[0].price <= 0.26 * 1000.0
    assert buys[1].size * buys[1].price <= 0.26 * 1000.0
    assert sum(trade.size for trade in buys) <= sells[0].size + 1e-9
