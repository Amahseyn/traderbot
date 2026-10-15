"""Online logistic-regression signal on OHLCV features, trained walk-forward.

Idea adapted from CloddsBot ``src/trading/ml-signals.ts`` (MIT License, Copyright (c) 2026
alsk1992): a sigmoid over a weighted feature vector (returns, volatility, RSI, momentum, volume)
updated by gradient steps. Rewritten for bars: orderbook/expiry features dropped, features are
standardized with running statistics, and a sample is only trained once its label is known
(``ml_horizon_bars`` later), so there is no lookahead.
"""

from __future__ import annotations

import math
from collections import deque

from traderbot.algorithms.base import Algorithm, Bar, SignalAction
from traderbot.algorithms.streaming import rsi_init, rsi_reset, rsi_update

FEATURE_COUNT = 6
MOMENTUM_BARS = 10
MAX_ABS_LOGIT = 30.0


class OnlineLogisticAlgorithm(Algorithm):
    """Predict P(close in ``ml_horizon_bars`` > close now). Buy above ``ml_buy_threshold``,
    sell below ``ml_sell_threshold``; no signals until ``ml_warmup_samples`` labelled samples."""

    name = "online_logistic"

    def __init__(
        self,
        *,
        period = 14,
        lookback_bars = 24,
        ml_horizon_bars = 6,
        ml_learning_rate = 0.05,
        ml_buy_threshold = 0.55,
        ml_sell_threshold = 0.45,
        ml_warmup_samples = 100,
    ):
        if lookback_bars < MOMENTUM_BARS:
            raise ValueError(f"lookback_bars must be >= {MOMENTUM_BARS}")
        if ml_horizon_bars < 1 or ml_warmup_samples < 1:
            raise ValueError("ml_horizon_bars and ml_warmup_samples must be >= 1")
        if ml_learning_rate <= 0:
            raise ValueError("ml_learning_rate must be positive")
        if not 0 < ml_sell_threshold <= ml_buy_threshold < 1:
            raise ValueError("need 0 < ml_sell_threshold <= ml_buy_threshold < 1")
        self.period = period
        self.lookback_bars = lookback_bars
        self.ml_horizon_bars = ml_horizon_bars
        self.ml_learning_rate = ml_learning_rate
        self.ml_buy_threshold = ml_buy_threshold
        self.ml_sell_threshold = ml_sell_threshold
        self.ml_warmup_samples = ml_warmup_samples
        self.reset()

    def reset(self) -> None:
        self._rsi = rsi_init(self.period)
        rsi_reset(self._rsi)
        self._closes: deque[float] = deque(maxlen=self.lookback_bars + 1)
        self._volumes: deque[float] = deque(maxlen=self.lookback_bars)
        self._pending: deque[tuple[list[float], float]] = deque()
        self._weights = [0.0] * FEATURE_COUNT
        self._bias = 0.0
        self._feature_count = 0
        self._feature_means = [0.0] * FEATURE_COUNT
        self._feature_m2 = [0.0] * FEATURE_COUNT
        self._trained_samples = 0
        self._in_position = False
        self.last_probability: float | None = None

    def sync_open_position(self, in_position: bool) -> None:
        self._in_position = in_position

    def _raw_features(self, close: float, volume: float, rsi_value: float) -> list[float] | None:
        closes = list(self._closes)
        if len(closes) < self.lookback_bars + 1 or len(self._volumes) < self.lookback_bars:
            return None
        returns = [closes[index] / closes[index - 1] - 1.0 for index in range(1, len(closes)) if closes[index - 1] > 0]
        if len(returns) < 2:
            return None
        mean_return = sum(returns) / len(returns)
        volatility = math.sqrt(sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1))
        average_volume = sum(self._volumes) / len(self._volumes)
        return [
            returns[-1],
            close / closes[0] - 1.0,
            volatility,
            (rsi_value - 50.0) / 50.0,
            close / closes[-1 - MOMENTUM_BARS] - 1.0,
            (volume / average_volume - 1.0) if average_volume > 0 else 0.0,
        ]

    def _standardize(self, raw: list[float]) -> list[float]:
        self._feature_count += 1
        scaled: list[float] = []
        for index, value in enumerate(raw):
            delta = value - self._feature_means[index]
            self._feature_means[index] += delta / self._feature_count
            self._feature_m2[index] += delta * (value - self._feature_means[index])
            variance = self._feature_m2[index] / (self._feature_count - 1) if self._feature_count > 1 else 0.0
            scaled.append(delta / math.sqrt(variance) if variance > 0 else 0.0)
        return scaled

    def _probability(self, features: list[float]) -> float:
        logit = self._bias + sum(weight * value for weight, value in zip(self._weights, features))
        logit = max(-MAX_ABS_LOGIT, min(MAX_ABS_LOGIT, logit))
        return 1.0 / (1.0 + math.exp(-logit))

    def _train_matured(self, close: float) -> None:
        while len(self._pending) > self.ml_horizon_bars:
            features, entry_close = self._pending.popleft()
            label = 1.0 if close > entry_close else 0.0
            error = self._probability(features) - label
            self._bias -= self.ml_learning_rate * error
            for index, value in enumerate(features):
                self._weights[index] -= self.ml_learning_rate * error * value
            self._trained_samples += 1

    def on_bar(self, bar: Bar) -> SignalAction:
        close = float(bar["close"])
        volume = float(bar.get("volume") or 0.0)
        rsi_value = rsi_update(self._rsi, close)
        raw = self._raw_features(close, volume, rsi_value) if rsi_value is not None else None
        self._closes.append(close)
        self._volumes.append(volume)
        if raw is None:
            return "hold"
        features = self._standardize(raw)
        self._pending.append((features, close))
        # The sample from ``ml_horizon_bars`` ago is labelled by this bar's close.
        self._train_matured(close)
        if self._trained_samples < self.ml_warmup_samples:
            return "hold"
        probability = self._probability(features)
        self.last_probability = probability
        if not self._in_position and probability >= self.ml_buy_threshold:
            self._in_position = True
            return "buy"
        if self._in_position and probability <= self.ml_sell_threshold:
            self._in_position = False
            return "sell"
        return "hold"
