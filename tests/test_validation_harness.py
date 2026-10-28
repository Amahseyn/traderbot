from traderbot.algorithms.cli_args import default_strategy_namespace
from traderbot.backtesting.metrics import split_chronological
from traderbot.backtesting.validation import ValidationOptions, run_strategy_validation


def _bars(closes: list[float]) -> list[dict]:
    return [
        {
            "timestamp": index * 60,
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": 1.0,
        }
        for index, close in enumerate(closes)
    ]


def test_split_chronological_partitions():
    bars = _bars([float(index) for index in range(100)])
    train, validation, test = split_chronological(bars, train_fraction=0.6, validation_fraction=0.2)
    assert len(train) == 60
    assert len(validation) == 20
    assert len(test) == 20
    assert train[-1]["close"] == 59.0
    assert test[0]["close"] == 80.0


def test_split_chronological_with_warmup_prepends_lookback():
    """warmup_bars prepends trailing bars from the preceding slice so indicator
    strategies have lookback on the first non-warmup bar (item 7)."""
    bars = _bars([float(index) for index in range(100)])
    train, validation, test = split_chronological(
        bars, train_fraction=0.6, validation_fraction=0.2, warmup_bars=10
    )
    assert len(train) == 60
    # validation = 10 warmup (bars 50-59) + 20 core (bars 60-79)
    assert len(validation) == 30
    assert validation[0]["close"] == 50.0  # warmup bar from train tail
    assert validation[10]["close"] == 60.0  # first core validation bar
    # test = 10 warmup (bars 70-79) + 20 core (bars 80-99)
    assert len(test) == 30
    assert test[0]["close"] == 70.0  # warmup bar from validation tail
    assert test[10]["close"] == 80.0  # first core test bar


def test_validation_selects_on_validation_not_test():
    closes = [100.0 + index for index in range(120)]
    payload = run_strategy_validation(
        ValidationOptions(
            strategy_id="sma_cross",
            param_grid={"fast": [3, 8], "slow": [12, 20]},
            bars=_bars(closes),
            min_trades=0,
            train_fraction=0.5,
            validation_fraction=0.25,
        ),
        default_strategy_namespace(),
    )
    assert payload["selection"] == "validation_return_pct"
    assert payload["selected_params"]
    assert "buy_and_hold_return_pct" in payload["test"]
    assert payload["combos_tried"] == 4
    assert len(payload["candidates"]) == 4
