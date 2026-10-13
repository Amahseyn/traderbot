from pathlib import Path

from traderbot.algorithms.optimized_params import quote_bucket_for_symbol, symbol_from_csv_path


def test_symbol_from_csv_path():
    assert symbol_from_csv_path(Path("BTCIRT_60.csv")) == "BTCIRT"
    assert symbol_from_csv_path(Path("ETHUSDT_240.csv")) == "ETHUSDT"


def test_quote_bucket_for_symbol():
    assert quote_bucket_for_symbol("BTCIRT") == "rls"
    assert quote_bucket_for_symbol("ETHUSDT") == "usdt"
