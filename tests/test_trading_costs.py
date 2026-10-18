from dataclasses import dataclass
from pathlib import Path

from traderbot.utils.trading_costs import (
    DEFAULT_SLIPPAGE_RATE,
    DEFAULT_TRADE_FEE_RATE,
    ResolvesCostRates,
    backtest_cost_rates,
    infer_exchange,
    resolve_cost_rates,
)


def test_default_fee_matches_hyperliquid_base_taker():
    assert DEFAULT_TRADE_FEE_RATE == 0.00045


def test_default_slippage_matches_live_trading_doc():
    # docs/live-trading.md: 0.045% fee and 0.05% slippage per taker fill.
    assert DEFAULT_SLIPPAGE_RATE == 0.0005


def test_hyperliquid_backtest_costs():
    fee, slip = backtest_cost_rates("hyperliquid", fee_role="taker")
    assert fee == 0.00045
    assert slip == 0.0005
    maker_fee, maker_slip = backtest_cost_rates("hyperliquid", fee_role="maker")
    assert maker_fee == 0.00015
    assert maker_slip == 0.0


def test_infer_exchange_from_csv_names():
    assert infer_exchange("data/BTCIRT_1.csv") == "nobitex"
    assert infer_exchange("results/x/ADAIRT_5") == "nobitex"
    assert infer_exchange(Path("data/hyperliquid/BTCUSDT_1.csv")) == "hyperliquid"
    assert infer_exchange("data/BTCUSDT_1.csv") is None
    assert infer_exchange(None) is None


def test_resolve_cost_rates_uses_nobitex_profile_for_irt_csv():
    assert resolve_cost_rates(source="data/BTCIRT_1.csv") == (0.0035, 0.001)
    # explicit values always win
    assert resolve_cost_rates(source="data/BTCIRT_1.csv", fee=0.001, slippage=0.0) == (0.001, 0.0)
    # explicit exchange beats the name
    assert resolve_cost_rates(exchange="hyperliquid", source="data/BTCIRT_1.csv") == (0.00045, 0.0005)


def test_options_mixin_resolves_from_csv_and_bars():
    @dataclass
    class Opts(ResolvesCostRates):
        csv_path: Path | None = None
        bars: list | None = None
        fee: float | None = None
        slippage: float | None = None
        exchange: str | None = None

    assert (Opts(csv_path=Path("data/ETHIRT_5.csv")).fee, Opts(csv_path=Path("data/ETHIRT_5.csv")).slippage) == (0.0035, 0.001)
    bars_opts = Opts(bars=[{"symbol": "BTCIRT", "close": 1.0}])
    assert bars_opts.fee == 0.0035
    hl = Opts(bars=[{"symbol": "BTCUSDT"}])
    assert (hl.fee, hl.slippage) == (0.00045, 0.0005)
    explicit = Opts(csv_path=Path("data/BTCIRT_1.csv"), fee=0.0)
    assert explicit.fee == 0.0 and explicit.slippage == 0.001


def test_sweep_options_resolve_nobitex_costs():
    from traderbot.backtesting.sweep import SweepOptions

    options = SweepOptions(strategy_id="sma_cross", param_grid={"fast": [3]}, csv_path=Path("data/BTCIRT_1.csv"))
    assert options.fee == 0.0035
    assert options.slippage == 0.001
