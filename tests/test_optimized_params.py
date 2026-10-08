from pathlib import Path

from traderbot.algorithms.optimized_params import symbol_from_csv_path


def test_symbol_from_csv_path():
    assert symbol_from_csv_path(Path("BTCIRT_60.csv")) == "BTCIRT"
    assert symbol_from_csv_path(Path("ETHUSDT_240.csv")) == "ETHUSDT"
