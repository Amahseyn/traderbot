from traderbot.traders.bot_inventory import BotInventory


def test_record_sell_releases_quote_reserved_on_full_exit():
    inventory = BotInventory(quote_currency="usdt", capital_cap=1000.0)
    inventory.record_buy(quote_spent=100.0, base_received=1.0, price=100.0)
    assert inventory.quote_reserved == 100.0
    assert inventory.base_amount == 1.0

    sold = inventory.record_sell(base_sold=1.0)
    assert sold == 1.0
    assert inventory.base_amount == 0.0
    assert inventory.quote_reserved == 0.0
    assert inventory.spendable_quote(1000.0) == 1000.0


def test_record_sell_releases_quote_reserved_proportionally():
    inventory = BotInventory(quote_currency="usdt", capital_cap=1000.0)
    inventory.record_buy(quote_spent=100.0, base_received=2.0, price=50.0)
    inventory.record_sell(base_sold=1.0)
    assert inventory.base_amount == 1.0
    assert inventory.quote_reserved == 50.0


def test_buy_sell_cycle_restores_spendable_quote():
    inventory = BotInventory(quote_currency="usdt", capital_cap=200.0)
    wallet = 200.0
    for _ in range(3):
        spendable = inventory.spendable_quote(wallet)
        inventory.record_buy(quote_spent=spendable, base_received=spendable / 10.0, price=10.0)
        inventory.record_sell(base_sold=inventory.base_amount)
        assert inventory.quote_reserved == 0.0
        assert inventory.spendable_quote(wallet) == 200.0
