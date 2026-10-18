"""
Causal intraday perp environment for RL research (training lives outside traderbot).

Reward includes bar return, taker fee on turnover, funding, and slippage. Observations
use only bars whose close time is <= the current step (no lookahead).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class PerpRlEnvConfig:
    fee_rate: float = 0.00045
    slippage_rate: float = 0.0001
    funding_rate_per_bar: float = 0.0
    max_position: float = 1.0


class PerpRlEnv:
    """
    Minimal Gym-style env: position in [-1, 1], one step per bar.

    ``reset`` / ``step`` return ``(obs, reward, done, info)`` for compatibility with
    custom trainers; does not depend on gymnasium.
    """

    def __init__(
        self,
        closes: np.ndarray,
        *,
        config: PerpRlEnvConfig | None = None,
        feature_window: int = 8,
    ):
        if len(closes) < feature_window + 2:
            raise ValueError("closes too short for feature_window")
        self.closes = np.asarray(closes, dtype=float)
        self.config = config or PerpRlEnvConfig()
        self.feature_window = feature_window
        self._index = feature_window
        self._position = 0.0

    def reset(self) -> tuple[np.ndarray, dict[str, Any]]:
        self._index = self.feature_window
        self._position = 0.0
        return self._observation(), {}

    def step(self, action: float) -> tuple[np.ndarray, float, bool, dict[str, Any]]:
        target = float(np.clip(action, -self.config.max_position, self.config.max_position))
        prev_close = self.closes[self._index - 1]
        close = self.closes[self._index]
        bar_return = (close / prev_close - 1.0) if prev_close > 0 else 0.0
        turnover = abs(target - self._position)
        fee = turnover * self.config.fee_rate
        slippage = turnover * self.config.slippage_rate
        funding = abs(target) * self.config.funding_rate_per_bar
        pnl = self._position * bar_return - fee - slippage - funding
        self._position = target
        self._index += 1
        done = self._index >= len(self.closes) - 1
        info = {
            "bar_return": bar_return,
            "turnover": turnover,
            "fee": fee,
            "funding": funding,
        }
        obs = self._observation() if not done else self._observation_at(self._index - 1)
        return obs, float(pnl), done, info

    def _observation_at(self, end_index: int) -> np.ndarray:
        window = self.closes[end_index - self.feature_window + 1 : end_index + 1]
        rets = np.diff(window) / window[:-1]
        pos = np.array([self._position], dtype=float)
        return np.concatenate([rets, pos])

    def _observation(self) -> np.ndarray:
        return self._observation_at(self._index)
