"""Vendored, point-in-time-correct FinRL-Trading code needed by traderbot.

These modules are self-contained copies of the FinRL-Trading sources that
traderbot consumed across a repository boundary. Keeping them here means
traderbot no longer needs the sibling ``FinRL-Trading`` checkout on
``sys.path`` for leakage checks, the intraday engine, or ML weight allocation.

Fixes applied relative to the upstream copies:

* ``ml_strategy`` now passes a per-rebalance ``as_of_date`` into
  ``allocate_weights`` on the rolling and sector-rolling paths, so the
  min-variance covariance only uses data up to the rebalance date
  (upstream used the full sample, leaking future prices).
* ``ml_strategy`` no longer mutates ``sys.path`` at import time; the
  optional ``yfinance``-based data fetchers are imported lazily.

The ``ml_strategy`` import pulls in scikit-learn, so it is exposed lazily:
importing :mod:`traderbot.finrl` works even when scikit-learn is unavailable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from traderbot.finrl.base_strategy import BaseStrategy, StrategyConfig, StrategyResult
from traderbot.finrl.drl_selection_utils import (
    merge_selection_meta,
    split_validation_for_model_selection,
)
from traderbot.finrl.feature_normalize import zscore_normalize_indicators
from traderbot.finrl.intraday_engine import (
    IntradayBacktestResult,
    ema_cross_signals,
    run_intraday_backtest,
)
from traderbot.finrl.intraday_experiment import (
    bars_to_ohlcv_frame,
    run_hyperliquid_intraday_experiment,
)
from traderbot.finrl.window_metrics import equity_window_metrics

if TYPE_CHECKING:  # pragma: no cover - typing only
    from traderbot.finrl.ml_strategy import MLStockSelectionStrategy, SectorNeutralMLStrategy

_LAZY = {
    "MLStockSelectionStrategy": "traderbot.finrl.ml_strategy",
    "SectorNeutralMLStrategy": "traderbot.finrl.ml_strategy",
}


def __getattr__(name: str) -> Any:
    module_name = _LAZY.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib

    return getattr(importlib.import_module(module_name), name)


__all__ = [
    "BaseStrategy",
    "StrategyConfig",
    "StrategyResult",
    "IntradayBacktestResult",
    "ema_cross_signals",
    "run_intraday_backtest",
    "equity_window_metrics",
    "zscore_normalize_indicators",
    "split_validation_for_model_selection",
    "merge_selection_meta",
    "bars_to_ohlcv_frame",
    "run_hyperliquid_intraday_experiment",
    "MLStockSelectionStrategy",
    "SectorNeutralMLStrategy",
]
