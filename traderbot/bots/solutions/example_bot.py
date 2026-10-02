from traderbot.algorithms.strategies.example import SmaCrossAlgorithm
from traderbot.bots.base import Bot
from traderbot.traders.strategies.algorithm_trader import AlgorithmTrader


def build_bot() -> Bot:
    algo = SmaCrossAlgorithm(fast=5, slow=20)
    trader = AlgorithmTrader.from_env(
        algo,
        bar_source=lambda: None,  # set e.g. latest candle from market_data / your feed
    )
    return Bot([trader], interval_sec=60.0)


if __name__ == "__main__":
    build_bot().run()
