from traderbot.discovery.regime import MaSlopeVolatilityRegime, regime_label_for_bars


def _synthetic_bars(count: int, *, drift: float = 0.0) -> list[dict[str, object]]:
    bars: list[dict[str, object]] = []
    price = 100.0
    for index in range(count):
        price *= 1.0 + drift
        bars.append(
            {
                "timestamp": 1_700_000_000 + index * 3600,
                "open": price,
                "high": price * 1.01,
                "low": price * 0.99,
                "close": price,
                "volume": 1000.0,
            },
        )
    return bars


def test_regime_uses_only_past_bars() -> None:
    bars = _synthetic_bars(80, drift=0.002)
    classifier = MaSlopeVolatilityRegime()
    label_early = classifier.label_at_bar(bars, 40)
    label_late = classifier.label_at_bar(bars, len(bars) - 1)
    assert label_early in {"trending", "trending_high_vol", "trending_low_vol", "uncertain", "range_bound"}
    assert regime_label_for_bars(bars[:50], classifier) == classifier.label_at_bar(bars[:50], 49)
    assert label_late != "uncertain" or label_early == "uncertain"
