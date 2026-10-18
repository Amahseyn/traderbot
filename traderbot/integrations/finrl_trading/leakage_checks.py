"""Static FinRL leakage checks, run against traderbot's vendored FinRL core.

These historically imported the sibling ``FinRL-Trading`` repo. They now use
:mod:`traderbot.finrl`, so the checks are self-contained.
"""

from __future__ import annotations

from typing import Any


def run_finrl_static_leakage_checks() -> list[dict[str, Any]]:
    """Run importable FinRL checks; skip gracefully if pandas is missing."""
    steps: list[dict[str, Any]] = []
    try:
        import pandas as pd  # noqa: F401
    except ModuleNotFoundError as exc:
        return [{"finrl_leakage": "skipped", "reason": str(exc)}]

    import pandas as pd

    from traderbot.finrl.intraday_engine import ema_cross_signals

    close = pd.Series([100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109] * 5, dtype=float)
    pos = ema_cross_signals(close, fast=3, slow=5)
    fast = close.ewm(span=3, adjust=False).mean()
    slow = close.ewm(span=5, adjust=False).mean()
    raw = (fast > slow).astype(int)
    for i in range(1, len(close)):
        if int(pos.iloc[i]) != int(raw.iloc[i - 1]):
            raise AssertionError(f"ema_cross_signals lag mismatch at {i}")
    steps.append({"finrl_ema_shift": "pass"})

    try:
        from traderbot.finrl.base_strategy import StrategyConfig
        from traderbot.finrl.ml_strategy import MLStockSelectionStrategy

        strategy = MLStockSelectionStrategy(StrategyConfig(name="leak_check"))
        fundamentals = _synthetic_fundamentals()
        as_of = fundamentals["datadate"].iloc[4]
        selected = pd.DataFrame({"gvkey": ["T0", "T1"], "predicted_return": [0.1, 0.2]})
        w1 = strategy.allocate_weights(
            selected,
            method="min_variance",
            fundamentals=fundamentals,
            as_of_date=as_of,
            lookback_periods=3,
        )
        tampered = fundamentals.copy()
        tampered.loc[tampered["datadate"] > as_of, "adj_close_q"] *= 10.0
        w2 = strategy.allocate_weights(
            selected,
            method="min_variance",
            fundamentals=tampered,
            as_of_date=as_of,
            lookback_periods=3,
        )
        if not (w1["weight"].round(6).equals(w2["weight"].round(6))):
            raise AssertionError("min_variance weights changed under future price tampering")
        steps.append({"finrl_min_variance_as_of": "pass"})
    except ModuleNotFoundError as exc:
        steps.append({"finrl_min_variance_as_of": "skipped", "reason": str(exc)})
    return steps


def _synthetic_fundamentals():
    import pandas as pd

    dates = pd.date_range("2020-03-31", periods=8, freq="QE")
    rows = []
    for quarter_index, datadate in enumerate(dates):
        for ticker_index in range(2):
            rows.append(
                {
                    "gvkey": f"T{ticker_index}",
                    "tic": f"T{ticker_index}",
                    "datadate": datadate,
                    "adj_close_q": 100.0 + quarter_index * 5 + ticker_index,
                    "feat_a": float(quarter_index),
                    "y_return": 0.02,
                    "y_return_provisional": False,
                }
            )
    return pd.DataFrame(rows)
