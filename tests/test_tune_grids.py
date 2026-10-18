from traderbot.backtesting.robust_defaults import validate_tune_grids


def test_default_tune_grids_cover_all_backtest_strategies():
    validate_tune_grids(full=False)


def test_full_tune_grids_cover_all_backtest_strategies():
    validate_tune_grids(full=True)
