"""Order placement idempotency and client order ID management for Traderbot.

Derived from the institutional 'order-placement-idempotency' skill:
1. Deterministic, collision-resistant client order IDs (idempotency keys).
2. Write-ahead intent tracking (PENDING -> PLACED / REJECTED / UNKNOWN).
3. Tri-state classification of broker responses: timeouts and connection drops
   are classified as UNKNOWN (never FAILED / REJECTED), preventing catastrophic
   duplicate orders upon retry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "OrderIntentState",
    "generate_client_order_id",
    "classify_network_or_broker_error",
    "InMemoryOrderLedger",
]


class OrderIntentState(str, Enum):
    PENDING = "PENDING"
    PLACED = "PLACED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


def generate_client_order_id(
    strategy_id: str,
    symbol: str,
    bar_timestamp: int,
    action: str,
    *,
    nonce: int = 0,
    max_length: int = 36,
) -> str:
    """Generate a deterministic, broker-safe client order ID.

    Combines strategy context, symbol, bar timestamp, action, and nonce into a
    truncated hash digest that fits within exchange client ID length limits.
    """
    raw_key = f"{strategy_id}:{symbol}:{bar_timestamp}:{action}:{nonce}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
    # Format: tb-<prefix>-<digest>
    prefix = f"{strategy_id[:6]}-{symbol[:6]}".lower().replace("/", "-")
    client_id = f"tb-{prefix}-{digest}"
    return client_id[:max_length]


def classify_network_or_broker_error(exc: Exception) -> OrderIntentState:
    """Classify an exception from an order dispatch call.

    Rule: A timeout, 5xx, or network reset means UNKNOWN (the exchange may have
    received and executed the order). Only explicit validation/rejection errors
    mean REJECTED.
    """
    msg = str(exc).lower()
    transient_indicators = [
        "timeout",
        "timed out",
        "connection",
        "network",
        "reset by peer",
        "gateway",
        "502",
        "503",
        "504",
    ]
    if any(ind in msg for ind in transient_indicators):
        return OrderIntentState.UNKNOWN
    return OrderIntentState.REJECTED


@dataclass
class OrderIntent:
    client_order_id: str
    symbol: str
    action: str
    size: float
    price: float | None
    state: OrderIntentState = OrderIntentState.PENDING
    broker_order_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_message: str | None = None


class InMemoryOrderLedger:
    """In-memory write-ahead order ledger preventing duplicate dispatches."""

    def __init__(self) -> None:
        self._intents: dict[str, OrderIntent] = {}

    def begin_intent(
        self,
        client_order_id: str,
        symbol: str,
        action: str,
        size: float,
        price: float | None = None,
    ) -> OrderIntent:
        """Register a PENDING intent before calling broker API.

        Raises ValueError if an intent for client_order_id is already active.
        """
        existing = self._intents.get(client_order_id)
        if existing and existing.state in (OrderIntentState.PENDING, OrderIntentState.PLACED):
            raise ValueError(
                f"Duplicate order dispatch blocked: {client_order_id} is already in state {existing.state}"
            )

        intent = OrderIntent(
            client_order_id=client_order_id,
            symbol=symbol,
            action=action,
            size=size,
            price=price,
            state=OrderIntentState.PENDING,
        )
        self._intents[client_order_id] = intent
        return intent

    def mark_placed(self, client_order_id: str, broker_order_id: str | int) -> None:
        intent = self._intents.get(client_order_id)
        if intent:
            intent.state = OrderIntentState.PLACED
            intent.broker_order_id = str(broker_order_id)
            intent.updated_at = datetime.now(timezone.utc).isoformat()

    def mark_failed(self, client_order_id: str, exc: Exception) -> OrderIntentState:
        intent = self._intents.get(client_order_id)
        classification = classify_network_or_broker_error(exc)
        if intent:
            intent.state = classification
            intent.error_message = str(exc)
            intent.updated_at = datetime.now(timezone.utc).isoformat()
        return classification

    def get_intent(self, client_order_id: str) -> OrderIntent | None:
        return self._intents.get(client_order_id)

    def is_safe_to_retry(self, client_order_id: str) -> bool:
        """Only safe to retry if explicitly REJECTED. UNKNOWN requires reconciliation."""
        intent = self._intents.get(client_order_id)
        if not intent:
            return True
        return intent.state == OrderIntentState.REJECTED

