from __future__ import annotations

import pytest
from traderbot.terminal.order_idempotency import (
    InMemoryOrderLedger,
    OrderIntentState,
    classify_network_or_broker_error,
    generate_client_order_id,
)


def test_generate_client_order_id_deterministic() -> None:
    id1 = generate_client_order_id("rsi_mr", "BTC/USDT", 1700000000, "buy")
    id2 = generate_client_order_id("rsi_mr", "BTC/USDT", 1700000000, "buy")
    assert id1 == id2
    assert len(id1) <= 36

    # Different nonce or action yields different id
    id_sell = generate_client_order_id("rsi_mr", "BTC/USDT", 1700000000, "sell")
    assert id1 != id_sell


def test_classify_network_or_broker_error() -> None:
    timeout_exc = TimeoutError("Connection timed out waiting for exchange 504 Gateway")
    assert classify_network_or_broker_error(timeout_exc) == OrderIntentState.UNKNOWN

    validation_exc = ValueError("Invalid order quantity: below minimum lot size")
    assert classify_network_or_broker_error(validation_exc) == OrderIntentState.REJECTED


def test_in_memory_ledger_duplicate_prevention() -> None:
    ledger = InMemoryOrderLedger()
    cid = generate_client_order_id("sma_cross", "ETH/USDT", 1700000000, "buy")

    # First begin_intent succeeds
    intent = ledger.begin_intent(cid, "ETH/USDT", "buy", 1.5, 2000.0)
    assert intent.state == OrderIntentState.PENDING

    # Attempting to begin same intent while PENDING raises ValueError
    with pytest.raises(ValueError, match="Duplicate order dispatch blocked"):
        ledger.begin_intent(cid, "ETH/USDT", "buy", 1.5, 2000.0)

    # Mark placed
    ledger.mark_placed(cid, "hl_order_999888")
    assert ledger.get_intent(cid).state == OrderIntentState.PLACED
    assert ledger.is_safe_to_retry(cid) is False

    # Attempting to begin same intent while PLACED also raises ValueError
    with pytest.raises(ValueError, match="Duplicate order dispatch blocked"):
        ledger.begin_intent(cid, "ETH/USDT", "buy", 1.5, 2000.0)


def test_in_memory_ledger_unknown_requires_reconciliation() -> None:
    ledger = InMemoryOrderLedger()
    cid = generate_client_order_id("sma_cross", "SOL/USDT", 1700000000, "buy")
    ledger.begin_intent(cid, "SOL/USDT", "buy", 10.0, 50.0)

    # Fail with network error
    status = ledger.mark_failed(cid, ConnectionResetError("Connection reset by peer"))
    assert status == OrderIntentState.UNKNOWN
    # Must NOT be safe to blindly retry without reconciliation
    assert ledger.is_safe_to_retry(cid) is False

