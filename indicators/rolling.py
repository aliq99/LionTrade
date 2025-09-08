from collections import deque

import numpy as np


class RollingEMA:
    """O(1) complexity Exponential Moving Average."""

    def __init__(self, period: int):
        assert period > 0, "Period must be a positive integer"
        self.alpha = 2 / (period + 1)
        self.value = None

    def update(self, value: float) -> float:
        if self.value is None:
            self.value = value
        else:
            self.value = self.alpha * value + (1 - self.alpha) * self.value
        return self.value


class RollingRSI:
    """O(1) complexity Relative Strength Index."""

    def __init__(self, period: int = 14):
        self.period = period
        self.gains = RollingEMA(period)
        self.losses = RollingEMA(period)
        self.last_price = None

    def update(self, price: float) -> float:
        if self.last_price is None:
            self.last_price = price
            return 50.0  # Return neutral RSI for the first value

        delta = price - self.last_price
        gain = delta if delta > 0 else 0
        loss = -delta if delta < 0 else 0

        avg_gain = self.gains.update(gain)
        avg_loss = self.losses.update(loss)

        self.last_price = price

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi


class RollingZScore:
    """O(n) complexity Z-Score using a rolling window."""

    def __init__(self, period: int = 20):
        self.period = period
        self.values = deque(maxlen=period)

    def update(self, value: float) -> float:
        self.values.append(value)
        if len(self.values) < self.period:
            return None  # Not enough data yet

        data = np.array(self.values)
        mean = np.mean(data)
        std = np.std(data, ddof=1)

        if std < 1e-12:  # Avoid division by zero
            return 0.0

        return (value - mean) / std
