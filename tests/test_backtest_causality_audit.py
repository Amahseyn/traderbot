from __future__ import annotations

from traderbot.backtesting.engine import BacktestResult, Trade
from traderbot.backtesting.validation import audit_backtest_causality


def test_audit_backtest_causality_clean_next_open() -> None:
    trade1 = Trade(timestamp=1000, action="buy", price=100.0, size=1.0)
    trade2 = Trade(timestamp=1060, action="sell", price=105.0, size=1.0)
    result = BacktestResult(
        initial_cash=1000.0,
        final_equity=1005.0,
        trades=[trade1, trade2],
        execution="next_open",
    )

    audit = audit_backtest_causality(result)
    assert audit["is_causal"] is True
    assert audit["clean"] is True
    assert audit["execution_mode"] == "next_open"
    assert len(audit["findings"]) == 0


def test_audit_backtest_causality_flags_same_bar_close() -> None:
    trade = Trade(timestamp=1000, action="buy", price=100.0, size=1.0)
    result = BacktestResult(
        initial_cash=1000.0,
        final_equity=1000.0,
        trades=[trade],
        execution="close",
    )

    audit = audit_backtest_causality(result)
    assert audit["is_causal"] is False
    assert audit["clean"] is False
    assert len(audit["findings"]) == 1
    assert audit["findings"][0]["type"] == "SAME_BAR_FILL_CONTAMINATION"


def test_audit_backtest_causality_flags_timestamp_breach() -> None:
    # Out-of-order timestamps
    trade1 = Trade(timestamp=2000, action="buy", price=100.0, size=1.0)
    trade2 = Trade(timestamp=1000, action="sell", price=105.0, size=1.0)
    result = BacktestResult(
        initial_cash=1000.0,
        final_equity=1005.0,
        trades=[trade1, trade2],
        execution="next_open",
    )

    audit = audit_backtest_causality(result)
    assert audit["is_causal"] is False
    assert any(f["type"] == "TIMESTAMP_CAUSALITY_BREACH" for f in audit["findings"])

