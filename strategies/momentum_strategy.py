import logging
import time

from indicators.rolling import RollingEMA, RollingZScore


class MomentumStrategy:
    def __init__(self, cfg, metrics):  # MODIFIED: Added metrics parameter
        self.cfg = cfg
        self.metrics = metrics  # MODIFIED: Store metrics object
        self.log = logging.getLogger("momo")
        self.log.info("MomentumStrategy initialized.")

        self.ema = RollingEMA(int(getattr(cfg, "ema_len", 12)))
        self.zscore = RollingZScore(int(getattr(cfg, "zscore_len", 20)))

        self.last_signal_ts = 0
        self.pos = None

    def on_price(self, px: float):
        """Processes a single price update and returns a signal if conditions are met."""
        ema_val = self.ema.update(px)
        zscore_val = self.zscore.update(px)

        # Entry logic
        if self.pos is None and zscore_val is not None:
            momentum = px - ema_val
            if (
                momentum > 0
                and zscore_val > float(self.cfg.zscore_entry)
                and not self._cooldown()
            ):
                self.last_signal_ts = time.time()
                self.metrics.signals_total.labels(
                    action="enter_long", strategy="momentum"
                ).inc()
                return {"action": "enter_long", "price": px}

        # Exit logic
        if self.pos:
            tp = self.pos["entry"] * (1 + float(self.cfg.take_profit_pct))
            sl = self.pos["entry"] * (1 - float(self.cfg.stop_loss_pct))
            if px >= tp:
                self.metrics.signals_total.labels(
                    action="exit", strategy="momentum"
                ).inc()
                return {"action": "exit", "price": px, "reason": "tp"}
            if px <= sl:
                self.metrics.signals_total.labels(
                    action="exit", strategy="momentum"
                ).inc()
                return {"action": "exit", "price": px, "reason": "sl"}

        return None

    def _cooldown(self):
        return (time.time() - self.last_signal_ts) < int(self.cfg.cooldown_sec)
