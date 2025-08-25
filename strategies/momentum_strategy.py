import math
import time
import numpy as np
from collections import deque

# --- Math Helper Functions for this Strategy ---
def ema(prev, x, alpha):
    return alpha * x + (1 - alpha) * prev if prev is not None else x

def zscore(series, window=60):
    if len(series) < window:
        return 0.0
    arr = np.array(list(series))[-window:]
    mu = arr.mean()
    sd = arr.std(ddof=1)
    if sd < 1e-12:
        sd = 1.0
    return float((arr[-1] - mu) / sd)


# --- The Original Momentum Strategy Class ---
class MomentumStrategy:
    def __init__(self, cfg):
        self.cfg = cfg
        self.last_signal_ts = 0.0
        self.prices = deque(maxlen=max(cfg.ema_len, cfg.zscore_len) * 3)
        self._ema = None
        self.pos = None  # Example: {"side":"LONG","qty":float,"entry":float}
        self._tick = 0

    def on_price(self, px: float):
        """This method is for the momentum strategy and gets called by the live bot."""
        if px is None or px <= 0 or not math.isfinite(px):
            return None

        # --- Calculate Indicators ---
        alpha = 2 / (self.cfg.ema_len + 1)
        self._ema = ema(self._ema, px, alpha)
        self.prices.append(px)
        
        # --- Entry Logic ---
        if self.pos is None and len(self.prices) >= self.cfg.zscore_len:
            momentum = px - (self._ema or px)
            zs = zscore(self.prices, self.cfg.zscore_len)
            
            if momentum > 0 and zs > self.cfg.zscore_entry and not self._cooldown():
                self.last_signal_ts = time.time()
                return {"action": "enter_long", "price": px}

        # --- Exit Logic ---
        if self.pos:
            tp = self.pos["entry"] * (1 + self.cfg.take_profit_pct)
            sl = self.pos["entry"] * (1 + self.cfg.stop_loss_pct)
            
            if px >= tp:
                return {"action": "exit", "price": px, "reason": "tp"}
            if px <= sl:
                return {"action": "exit", "price": px, "reason": "sl"}

        return None

    def _cooldown(self):
        return (time.time() - self.last_signal_ts) < self.cfg.cooldown_sec