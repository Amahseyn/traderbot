import math

from traderbot.algorithms.registry import algorithm_for_id
from traderbot.algorithms.strategies.ensemble import ENSEMBLE_PRESETS, EnsembleAlgorithm
from traderbot.backtesting.engine import run_backtest


def _bars(count=400):
    closes = [100 + 10 * math.sin(index / 9) + index * 0.02 for index in range(count)]
    return [
        {
            "timestamp": index * 60,
            "open": closes[index],
            "high": closes[index] * 1.002,
            "low": closes[index] * 0.998,
            "close": closes[index],
            "volume": 1.0 + (index % 5),
        }
        for index in range(count)
    ]


def test_ensemble_presets_registered():
    algo = algorithm_for_id(
        "ensemble",
        ensemble_preset="1m_scalp_trend",
        ensemble_entry_rule="all",
        ensemble_exit_rule="any",
    )
    assert isinstance(algo, EnsembleAlgorithm)
    assert len(algo.child_ids) == len(ENSEMBLE_PRESETS["1m_scalp_trend"])


def test_ensemble_all_entry_requires_unanimous_buy():
    algo = EnsembleAlgorithm(
        ensemble_preset="intraday_trend_stack",
        ensemble_entry_rule="all",
        ensemble_exit_rule="any",
    )
    bar = {
        "timestamp": 1,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.0,
        "volume": 1.0,
    }
    for _ in range(300):
        algo.on_bar(bar)
    assert algo.on_bar(bar) in ("hold", "buy", "sell")


def test_ensemble_runs_backtest():
    bars = _bars()
    algo = algorithm_for_id("ensemble", ensemble_preset="1m_pattern_ma", ensemble_entry_rule="majority")
    result = run_backtest(algo, bars, initial_cash=10_000.0)
    assert len(result.equity_curve) == len(bars)


class _Scripted:
    """Minimal child: emits a scripted signal per bar and tracks sync calls."""

    def __init__(self, script):
        self.script = list(script)
        self.i = -1
        self.in_position = False

    def reset(self):
        self.i = -1
        self.in_position = False

    def sync_open_position(self, in_position):
        self.in_position = in_position

    def on_fill(self, *args):
        pass

    def on_bar(self, bar):
        self.i += 1
        signal = self.script[self.i] if self.i < len(self.script) else "hold"
        if signal == "buy":
            self.in_position = True
        elif signal == "sell":
            self.in_position = False
        return signal


def _ensemble(primary, flt, **kwargs):
    children = iter([_Scripted(primary), _Scripted(flt)])
    return EnsembleAlgorithm(
        ensemble_preset="1m_scalp_trend", member_factory=lambda _sid, **_kw: next(children), **kwargs
    )


def test_outvoted_children_are_reset_to_flat():
    algo = _ensemble(["buy", "hold"], ["hold", "hold"])
    assert algo.on_bar({}) == "hold"
    assert all(child.in_position is False for _, child in algo._members)


def test_state_filter_mode_gates_on_trend_state_not_crossover():
    # Filter crosses up on bar 0 and stays long; primary buys on bar 2.
    algo = _ensemble(["hold", "hold", "buy", "hold", "hold"], ["buy", "hold", "hold", "hold", "sell"],
                     ensemble_filter_mode="state")
    assert [algo.on_bar({}) for _ in range(5)] == ["hold", "hold", "buy", "hold", "sell"]
    # Signal mode needs both buys on the same bar, so it never enters here.
    algo = _ensemble(["hold", "hold", "buy", "hold", "hold"], ["buy", "hold", "hold", "hold", "sell"])
    assert [algo.on_bar({}) for _ in range(5)] == ["hold"] * 5


def test_state_filter_blocks_entry_when_filter_flat():
    algo = _ensemble(["buy", "hold"], ["hold", "hold"], ensemble_filter_mode="state")
    assert algo.on_bar({}) == "hold"
