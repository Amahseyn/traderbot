"""``target_exposure`` sizing for strategies that historically traded all-in.

Every signal strategy must accept ``target_exposure`` (fraction of equity per buy);
``1.0`` keeps the legacy all-in behavior, values below cap each buy and sell exits
fully. Covered here: registry/CLI wiring, per-strategy sizing, and engine fills.
"""

import pytest

from traderbot.algorithms.base import Algorithm, OrderSize
from traderbot.algorithms.cli_args import (
    add_strategy_param_flags,
    default_strategy_namespace,
)
from traderbot.algorithms.registry import (
    algorithm_for_id,
    strategy_kwargs_from_namespace,
    strategy_param_defaults,
)
from traderbot.backtesting import run_backtest
from traderbot.algorithms.strategies.ensemble import EnsembleAlgorithm

#: Strategies that were all-in/all-out before target_exposure existed.
SIZED_STRATEGY_IDS = (
    "sma_cross",
    "ema_cross",
    "rsi_threshold",
    "macd_cross",
    "bollinger_mean_reversion",
    "chart_patterns",
    "breakout_atr",
    "range_breakout",
    "rsi_trend",
    "rsi_divergence",
    "momentum_shock",
    "online_logistic",
    "finrl_ema_intraday",
    "ensemble",
    "spot_grid",
)

EXPOSURE = 0.25


def _bars(bars: list[dict]) -> list[dict]:
    return [
        {
            "timestamp": index + 1,
            **{key: float(bar[key]) for key in ("open", "high", "low", "close")},
            "volume": float(bar.get("volume", 1.0)),
        }
        for index, bar in enumerate(bars)
    ]


def _series(closes, highs=None, lows=None, volumes=None) -> list[dict]:
    return _bars(
        {
            "open": close,
            "high": high if high is not None else max(close, previous),
            "low": low if low is not None else min(close, previous),
            "close": close,
            "volume": volume if volume is not None else 1.0,
        }
        for index, (close, previous, high, low, volume) in enumerate(zip(
            closes,
            [closes[0]] + list(closes[:-1]),
            highs or [None] * len(closes),
            lows or [None] * len(closes),
            volumes or [None] * len(closes),
        ))
    )


def _signal_sizes(algorithm: Algorithm, bars: list[dict]) -> list[tuple[str, float | None]]:
    """(action, target_exposure) per bar; exposure is ``None`` for legacy all-in sizing."""
    pairs: list[tuple[str, float | None]] = []
    for bar in bars:
        action = algorithm.on_bar(bar)
        size = algorithm.order_size() if action != "hold" else None
        exposure = None if size is None else float(size.target_exposure)
        pairs.append((action, exposure))
    return pairs


# --- registry / CLI wiring -------------------------------------------------------------------


@pytest.mark.parametrize("strategy_id", SIZED_STRATEGY_IDS)
def test_namespace_wires_target_exposure(strategy_id: str) -> None:
    namespace = default_strategy_namespace(target_exposure=EXPOSURE)
    kwargs = strategy_kwargs_from_namespace(strategy_id, namespace)
    assert kwargs["target_exposure"] == EXPOSURE


@pytest.mark.parametrize("strategy_id", SIZED_STRATEGY_IDS)
def test_strategy_param_defaults_include_target_exposure(strategy_id: str) -> None:
    defaults = strategy_param_defaults(strategy_id)
    assert defaults.get("target_exposure") == 1.0


def test_cli_flag_target_exposure() -> None:
    parser = add_strategy_param_flags.__wrapped__(None) if False else None  # placeholder
    import argparse

    parser = argparse.ArgumentParser()
    add_strategy_param_flags(parser)
    args = parser.parse_args(["--target-exposure", "0.25"])
    assert args.target_exposure == 0.25


@pytest.mark.parametrize("strategy_id", SIZED_STRATEGY_IDS)
def test_accepts_target_exposure_kwarg(strategy_id: str) -> None:
    standout = {
        "spot_grid": {"start_price": 95.0, "end_price": 105.0},
    }
    algorithm = algorithm_for_id(strategy_id, target_exposure=EXPOSURE, **standout.get(strategy_id, {}))
    assert algorithm.order_size() is None
    with pytest.raises(ValueError):
        algorithm_for_id(strategy_id, target_exposure=0.0, **standout.get(strategy_id, {}))
    with pytest.raises(ValueError):
        algorithm_for_id(strategy_id, target_exposure=1.5, **standout.get(strategy_id, {}))


# --- signal-level sizing ---------------------------------------------------------------------

# Each builder takes target_exposure and returns (algorithm, bars): one bars series
# that produces at least one buy, and ideally a sell.

def _sma_cross_props(target_exposure: float):
    return algorithm_for_id("sma_cross", fast=2, slow=3, target_exposure=target_exposure), _series(
        [10.0, 10.0, 10.0, 11.0, 10.0, 9.0]
    )


def _ema_cross_props(target_exposure: float):
    return algorithm_for_id("ema_cross", fast=2, slow=3, target_exposure=target_exposure), _series(
        [10.0, 10.0, 10.0, 11.0, 10.0, 9.0]
    )


def _macd_props(target_exposure: float):
    return algorithm_for_id("macd_cross", fast=2, slow=3, signal=2, target_exposure=target_exposure), _series(
        [10.0, 10.0, 10.0, 11.0, 10.9, 10.8, 10.7, 10.6, 10.5, 10.4, 10.3]
    )


def _rsi_threshold_props(target_exposure: float):
    # Flat closes keep RSI at 50: buys fire (<= oversold), sells never (< overbought).
    return algorithm_for_id("rsi_threshold", period=2, oversold=55.0, overbought=60.0,
                            target_exposure=target_exposure), _series([10.0] * 6)


def _rsi_threshold_sell_props(target_exposure: float):
    # Rising closes push RSI over the overbought band; oversold unreachable.
    return algorithm_for_id("rsi_threshold", period=2, oversold=55.0, overbought=60.0,
                            target_exposure=target_exposure), _series([10.0, 9.5, 9.5, 10.0, 10.5])


def _bollinger_props(target_exposure: float):
    return algorithm_for_id("bollinger_mean_reversion", period=3, num_std=0.5,
                            target_exposure=target_exposure), _series([100.0, 100.0, 100.0, 105.0])


def _chart_patterns_props(target_exposure: float):
    return algorithm_for_id(
        "chart_patterns",
        swing_window_bars=1,
        min_swing_separation_bars=1,
        low_tolerance_ratio=0.02,
        pattern_score_threshold=0.35,
        target_exposure=target_exposure,
    ), _series(
        closes=[100.0, 100.0, 100.0, 100.0, 100.0, 103.0],
        highs=[100.0, 100.0, 102.0, 100.0, 100.0, 104.0],
        lows=[100.0, 99.0, 100.0, 99.0, 98.9, 103.0],
    )


def _breakout_atr_props(target_exposure: float):
    return algorithm_for_id(
        "breakout_atr", lookback_bars=4, atr_period=2, atr_multiplier=0.1, target_exposure=target_exposure
    ), _series(
        closes=[100.0] * 5 + [100.5, 99.0],
        highs=[100.0] * 5 + [100.5, 99.0],
        lows=[100.0] * 5 + [100.5, 99.0],
    )


def _range_breakout_props(target_exposure: float, series_bars: list[dict] | None = None):
    bars = [
        {
            "open": 99.5, "high": 100.0, "low": 99.0, "close": 99.5, "volume": 1.0,
        }
        for _ in range(10)
    ]
    bars.append({"open": 101.0, "high": 101.5, "low": 100.5, "close": 101.0, "volume": 2.0})
    return algorithm_for_id(
        "range_breakout", lookback_bars=10, target_exposure=target_exposure
    ), _bars(bars)


def _rsi_trend_props(target_exposure: float):
    return algorithm_for_id(
        "rsi_trend", period=2, rsi_trend_entry=51.0, rsi_trend_exit=49.0, trend_filter_period=2,
        target_exposure=target_exposure,
    ), _series([10.0, 9.5, 9.5, 10.0, 9.0])


def _rsi_divergence_props(target_exposure: float):
    return algorithm_for_id(
        "rsi_divergence",
        period=2,
        swing_window_bars=1,
        divergence_rsi_level=100.0,
        divergence_confirm_bars=2,
        target_exposure=target_exposure,
    ), _series(
        closes=[10.0, 9.8, 9.85, 9.9, 9.95, 9.95, 100.0, 8.0],
        highs=[10.0, 9.9, 9.9, 9.9, 9.9, 99.3, 100.0, 8.0],
        lows=[100.0, 100.0, 99.0, 101.0, 99.4, 98.9, 99.5, 8.0],
    )


class _ScriptedSource:
    def __init__(self, scores: list[float]):
        self._scores = list(scores)
        self._index = 0

    def reset(self) -> None:
        self._index = 0

    def score_bar(self, bar: dict) -> float:
        score = self._scores[min(self._index, len(self._scores) - 1)]
        self._index += 1
        return score


def _momentum_shock_props(target_exposure: float):
    return algorithm_for_id(
        "momentum_shock",
        shock_hold_bars=3,
        event_source=_ScriptedSource([0.0, 0.0, 1.0, 0.0, 0.0, -1.0]),
        target_exposure=target_exposure,
    ), _series([100.0] * 7)


def _online_logistic_props(target_exposure: float):
    return algorithm_for_id(
        "online_logistic",
        lookback_bars=24,
        ml_horizon_bars=1,
        ml_warmup_samples=1,
        ml_buy_threshold=0.4,
        ml_sell_threshold=0.25,
        target_exposure=target_exposure,
    ), _series([100.0] * 28)


def _finrl_props(target_exposure: float):
    return algorithm_for_id(
        "finrl_ema_intraday", fast=2, slow=3, target_exposure=target_exposure
    ), _series([10.0, 10.0, 10.0, 11.0, 10.0, 9.0])


def _spot_grid_props(target_exposure: float):
    return algorithm_for_id(
        "spot_grid", start_price=95.0, end_price=105.0, grid_count=5, target_exposure=target_exposure
    ), _series([100.0, 100.0, 106.0])


SIGNAL_SERIES = {
    "sma_cross": _sma_cross_props,
    "ema_cross": _ema_cross_props,
    "macd_cross": _macd_props,
    "rsi_threshold": _rsi_threshold_props,
    "rsi_threshold_sell": _rsi_threshold_sell_props,
    "bollinger_mean_reversion": _bollinger_props,
    "chart_patterns": _chart_patterns_props,
    "breakout_atr": _breakout_atr_props,
    "range_breakout": _range_breakout_props,
    "rsi_trend": _rsi_trend_props,
    "rsi_divergence": _rsi_divergence_props,
    "momentum_shock": _momentum_shock_props,
    "online_logistic": _online_logistic_props,
    "finrl_ema_intraday": _finrl_props,
    "spot_grid": _spot_grid_props,
}


@pytest.mark.parametrize("series_id", sorted(SIGNAL_SERIES))
def test_partial_exposure_sizes_signals(series_id: str) -> None:
    algorithm, bars = SIGNAL_SERIES[series_id](EXPOSURE)
    pairs = _signal_sizes(algorithm, bars)
    observations = {(action, exposure) for action, exposure in pairs if action != "hold"}
    bad = observations - {("buy", EXPOSURE), ("sell", 0.0)}
    assert bad == set(), f"{series_id}: unexpected (action, exposure) pairs {bad}"
    assert ("buy", EXPOSURE) in observations, f"{series_id}: expected a buys to exercise sizing"


@pytest.mark.parametrize("series_id", sorted(SIGNAL_SERIES))
def test_default_exposure_keeps_legacy_all_in(series_id: str) -> None:
    algorithm, bars = SIGNAL_SERIES[series_id](1.0)
    pairs = []
    for bar in bars:
        action = algorithm.on_bar(bar)
        size = algorithm.order_size() if action != "hold" else None
        pairs.append((action, size))
    assert all(size is None for _, size in pairs)


# --- ensemble --------------------------------------------------------------------------------


class _ScriptedMember(Algorithm):
    def __init__(self, actions: list[str]):
        self._actions = list(actions)
        self._index = 0

    def on_bar(self, bar: dict) -> str:  # type: ignore[type-arg]
        action = self._actions[min(self._index, len(self._actions) - 1)]
        self._index += 1
        return action  # type: ignore[return-value]


def _ensemble_factory(target_exposure: float) -> EnsembleAlgorithm:
    def factory(strategy_id: str, **kwargs: dict) -> Algorithm:
        return _ScriptedMember(["hold", "buy", "hold", "sell", "hold"])

    return EnsembleAlgorithm(
        ensemble_preset="1m_scalp_trend",
        ensemble_entry_rule="all",
        ensemble_exit_rule="all",
        target_exposure=target_exposure,
        member_factory=factory,
    )


def test_ensemble_partial_exposure() -> None:
    algorithm = _ensemble_factory(EXPOSURE)
    bars = _series([100.0] * 5)
    sizes: list[float | None] = []
    actions = []
    for bar in bars:
        action = algorithm.on_bar(bar)
        actions.append(action)
        sizes.append(float(algorithm.order_size().target_exposure) if action != "hold" else None)
    assert actions[1] == "buy"
    assert sizes[1] == EXPOSURE
    assert actions[3] == "sell"
    assert sizes[3] == 0.0


def test_ensemble_default_exposure_legacy() -> None:
    algorithm = _ensemble_factory(1.0)
    bars = _series([100.0] * 5)
    sizes = []
    actions = []
    for bar in bars:
        action = algorithm.on_bar(bar)
        actions.append(action)
        sizes.append(algorithm.order_size() if action != "hold" else None)
    assert actions[1] == "buy"
    assert all(size is None for size in sizes)


# --- engine fills ----------------------------------------------------------------------------


def test_engine_buy_spends_only_target_exposure() -> None:
    bars = _series(
        closes=[100.0] * 5 + [100.5, 99.0, 98.0],
        highs=[100.0] * 5 + [100.5, 99.0, 98.0],
        lows=[100.0] * 5 + [100.5, 99.0, 98.0],
    )
    algorithm = algorithm_for_id(
        "breakout_atr", lookback_bars=4, atr_period=2, atr_multiplier=0.1, target_exposure=EXPOSURE
    )
    result = run_backtest(algorithm, bars, initial_cash=1000.0, fee_rate=0.0)
    buys = [trade for trade in result.trades if trade.action == "buy"]
    sells = [trade for trade in result.trades if trade.action == "sell"]
    assert buys, "expected the breakout to buy"
    assert buys[0].size * buys[0].price <= 0.26 * 1000.0
    assert sells, "expected the breakdown to sell"
    assert sells[0].size >= buys[0].size - 1e-9


def test_engine_default_exposure_buys_full_cash() -> None:
    bars = _series(
        closes=[100.0] * 5 + [100.5, 99.0, 98.0],
        highs=[100.0] * 5 + [100.5, 99.0, 98.0],
        lows=[100.0] * 5 + [100.5, 99.0, 98.0],
    )
    algorithm = algorithm_for_id("breakout_atr", lookback_bars=4, atr_period=2, atr_multiplier=0.1)
    result = run_backtest(algorithm, bars, initial_cash=1000.0, fee_rate=0.0)
    buys = [trade for trade in result.trades if trade.action == "buy"]
    assert buys
    assert buys[0].size * buys[0].price >= 0.99 * 1000.0
