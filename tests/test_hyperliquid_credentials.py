import pytest

from traderbot.hyperliquid.credentials import normalize_wallet_address


def test_normalize_wallet_address():
    assert (
        normalize_wallet_address("0x47B36028469Bc21c07Ab2Bc31CEC60844e0cF799")
        == "0x47B36028469Bc21c07Ab2Bc31CEC60844e0cF799"
    )


def test_normalize_wallet_address_rejects_invalid():
    with pytest.raises(ValueError):
        normalize_wallet_address("not-a-wallet")
