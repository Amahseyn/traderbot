import time

from traderbot.bots.base import Bot
from traderbot.nobitex.client import NobitexClient
from traderbot.traders.base import Trader


class _Counter(Trader):
    def __init__(self, client: NobitexClient):
        super().__init__(client)
        self.n = 0

    def step(self) -> None:
        self.n += 1


def test_bot_run_once(keys):
    pub, priv = keys
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    t = _Counter(client)
    Bot([t]).run_once()
    assert t.n == 1


def test_bot_run_max_steps(keys):
    pub, priv = keys
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    t = _Counter(client)
    Bot([t], interval_sec=0).run(max_steps=3)
    assert t.n == 3


def test_bot_run_stops_during_interval(keys):
    pub, priv = keys
    client = NobitexClient(pub, priv, request_fn=lambda *_a, **_k: None)
    trader = _Counter(client)
    started = time.monotonic()
    Bot([trader], interval_sec=30).run(max_steps=5, should_stop=lambda: trader.n >= 1)
    assert trader.n == 1
    assert time.monotonic() - started < 2


def test_bot_aligns_sleep_to_bar_close_and_skips_sleep_when_bars_queued():
    from types import SimpleNamespace

    import pytest

    clock = {"now": 1_000_000.0 + 30.0}  # 30s into a 1m bar
    trader = SimpleNamespace(step=lambda: None, last_step_got_bar=True, bar_source=None)
    bot = Bot([trader], interval_sec=60.0, bar_seconds=60, close_delay_sec=1.0, clock=lambda: clock["now"])
    # 1_000_000 % 60 == 40 -> next close at +20s from the bar start; +1s publish delay.
    assert bot.next_sleep_seconds() == pytest.approx(60 - ((1_000_030.0 - 1.0) % 60))
    trader.bar_source = SimpleNamespace(pending=lambda: 3)
    assert bot.next_sleep_seconds() == 0.0
    # Just after a close with no new bar yet: retry quickly.
    trader.bar_source = None
    trader.last_step_got_bar = False
    clock["now"] = 1_000_020.0 + 3.0
    assert bot.next_sleep_seconds() == 2.0
    # Without alignment the old fixed interval applies.
    assert Bot([trader], interval_sec=7.0).next_sleep_seconds() == 7.0
