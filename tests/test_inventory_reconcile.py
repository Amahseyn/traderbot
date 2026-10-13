from traderbot.traders.bot_inventory import BotInventory
from traderbot.traders.inventory_reconcile import sync_inventory_to_exchange_base


def test_sync_inventory_shrinks_when_exchange_base_lower():
    inventory = BotInventory(quote_currency="usdt", capital_cap=1000.0)
    inventory.record_buy(quote_spent=100.0, base_received=1.0, price=100.0)
    changed = sync_inventory_to_exchange_base(inventory, 0.25, mark_price=100.0)
    assert changed is True
    assert inventory.base_amount == 0.25
    assert inventory.quote_reserved == 25.0


def test_sync_inventory_ignores_exchange_surplus():
    inventory = BotInventory(quote_currency="usdt", capital_cap=1000.0)
    inventory.record_buy(quote_spent=50.0, base_received=0.5, price=100.0)
    changed = sync_inventory_to_exchange_base(inventory, 2.0, mark_price=100.0)
    assert changed is False
    assert inventory.base_amount == 0.5
