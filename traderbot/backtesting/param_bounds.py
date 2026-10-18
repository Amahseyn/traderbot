"""Valid ranges for strategy knobs so tuning never proposes nonsense (negative stops, >100% sizes)."""

from __future__ import annotations

from typing import Any

#: Fractions of equity / probabilities / skews: must stay inside [low, high].
_UNIT_INTERVAL: dict[str, tuple[float, float]] = {
    "scalp_position_fraction": (0.05, 1.0),
    "mm_order_fraction": (0.05, 1.0),
    "mm_inventory_skew": (0.0, 1.0),
    "breakout_stop_fraction": (0.05, 1.0),
    "train_fraction": (0.05, 0.95),
    "validation_fraction": (0.05, 0.95),
    "ml_buy_threshold": (0.5, 0.99),
    "ml_sell_threshold": (0.01, 0.5),
    "pattern_tolerance_ratio": (0.001, 0.2),
    "pattern_score_threshold": (0.0, 1.0),
}

#: RSI-style levels on a 0..100 scale.
_LEVEL_0_100 = ("oversold", "overbought", "rsi_trend_entry", "rsi_trend_exit", "divergence_rsi_level")

#: Signed knobs (e.g. return filters) are left alone.
_SIGNED = ("buy_min_recent_return", "sell_max_recent_return", "buy_min_fine_last_5m", "sell_max_fine_last_5m")

#: Non-negative knobs where 0 means "off".
_ZERO_ALLOWED_SUFFIXES = ("trailing_stop_pct",)
_ZERO_ALLOWED = (
    "min_volume_ratio",
    "max_spread_pct",
    "mm_adverse_move_atr",
    "mm_stop_loss_pct",
    "mm_min_profit_pct",
    "mm_vol_spread_mult",
    "entry_offset_pct",
    "trend_max_adds",
    "cooldown_bars_after_loss",
    "context_bars",
    "grid_reanchor_bars",
)


def float_bounds(name: str, default: float) -> tuple[float, float]:
    """Search interval for a float knob around ``default`` that respects its valid range."""
    if name in _UNIT_INTERVAL:
        low_cap, high_cap = _UNIT_INTERVAL[name]
        width = max(abs(default) * 0.5, 0.05)
        return max(low_cap, default - width), min(high_cap, default + width)
    if name in _LEVEL_0_100:
        return max(1.0, default - 20.0), min(99.0, default + 20.0)
    if name in _SIGNED:
        magnitude = max(abs(default), 0.001)
        return default - magnitude * 2.0, default + magnitude * 2.0
    zero_ok = name in _ZERO_ALLOWED or name.endswith(_ZERO_ALLOWED_SUFFIXES)
    if default > 0:
        # Multiplicative range: never crosses zero, so stops/targets/spreads stay positive.
        return (0.0 if zero_ok else default / 4.0), default * 3.0
    if default == 0:
        return 0.0, 0.01 if ("pct" in name or "return" in name) else 1.0
    return default * 3.0, (0.0 if zero_ok else default / 4.0)


def param_value_error(name: str, value: Any) -> str | None:
    """Reason a value is invalid for ``name`` (``None`` when fine)."""
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if name in _UNIT_INTERVAL:
        low, high = _UNIT_INTERVAL[name]
        if not low <= number <= high:
            return f"{name}={value} outside [{low}, {high}]"
        return None
    if name in _LEVEL_0_100 and not 0 < number < 100:
        return f"{name}={value} must be in (0, 100)"
    if name in _SIGNED:
        return None
    if number < 0 and ("pct" in name or "fraction" in name or "mult" in name or "ratio" in name
                       or "period" in name or "bars" in name or name in _ZERO_ALLOWED):
        return f"{name}={value} must not be negative"
    if "fraction" in name and number > 1:
        return f"{name}={value} must be <= 1"
    return None
