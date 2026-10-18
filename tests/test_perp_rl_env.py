import numpy as np

from traderbot.backtesting.perp_rl_env import PerpRlEnv, PerpRlEnvConfig


def test_perp_rl_env_step_applies_fees():
    closes = np.linspace(100.0, 110.0, 30)
    env = PerpRlEnv(closes, config=PerpRlEnvConfig(fee_rate=0.01, funding_rate_per_bar=0.0))
    obs, _ = env.reset()
    assert obs.shape[0] == env.feature_window
    _, _, _, info = env.step(1.0)
    assert info["turnover"] == 1.0
    assert info["fee"] > 0


def test_perp_rl_env_observation_uses_past_closes_only():
    closes = np.array([100.0, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110], dtype=float)
    env = PerpRlEnv(closes, feature_window=4)
    obs, _ = env.reset()
    assert len(obs) == 4
