from traderbot.terminal.paper_portfolio import PaperPortfolio, default_paper_initial_cash


def test_default_paper_cash_by_dst():
    assert default_paper_initial_cash("usdt") == 1_000.0
    assert default_paper_initial_cash("rls") == 10_000_000.0


def test_paper_buy_sell_round_trip():
    portfolio = PaperPortfolio(quote_cash=1_000.0, quote_currency="usdt", fee_rate=0.0)
    buy = portfolio.apply_fill("buy", 100.0)
    assert buy["filled"] is True
    assert portfolio.quote_cash == 0.0
    assert portfolio.base_amount == 10.0

    sell = portfolio.apply_fill("sell", 110.0)
    assert sell["filled"] is True
    assert portfolio.base_amount == 0.0
    assert portfolio.quote_cash == 1_100.0
