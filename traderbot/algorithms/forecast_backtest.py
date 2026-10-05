from __future__ import annotations

from typing import Any

from traderbot.algorithms.registry import backtest_strategy_ids


def strategy_compare_plan(_mode: str | None) -> list[tuple[str, str, dict[str, Any]]]:
    """Rows for strategy compare: (result id, algorithm id, extra kwargs)."""
    return [(strategy_id, strategy_id, {}) for strategy_id in backtest_strategy_ids(include_forecast_strategies=False)]
