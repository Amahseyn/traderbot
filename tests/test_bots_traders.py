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
