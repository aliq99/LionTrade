import logging
import time
from collections import deque
from typing import Any, Dict, Optional


class RiskManager:
    def __init__(self, cfg, ai_analyzer, metrics=None):
        self.cfg = cfg
        self.log = logging.getLogger("momo")
        self.ai_analyzer = ai_analyzer
        self.metrics = metrics
        self.starting_budget = float(getattr(cfg, "total_budget_usdt", 0.0))
        self.trading_paused_drawdown = False
        self.trade_history = deque(maxlen=int(getattr(cfg, "throttle_window", 20)))
        self.trading_paused_throttle = False
        self.log.info("RiskManager initialized.")

    def start_day(self, equity: float) -> None:
        self.starting_budget = float(equity)
        self.trading_paused_drawdown = False

    def _win_rate(self) -> Optional[float]:
        if not self.trade_history:
            return None
        return sum(self.trade_history) / len(self.trade_history)

    def approve_trade(
        self,
        signal: Dict[str, Any],
        current_budget: float,
        book: Optional[Dict[str, float]] = None,
        now_ts: Optional[float] = None,  # MODIFIED: Added now_ts for backtesting
    ) -> bool:
        now = now_ts or time.time()  # MODIFIED: Use historical time if provided

        # 1) Stale AI sentiment guard
        last = float(getattr(self.ai_analyzer, "last_analysis_time", 0.0))
        max_age = float(getattr(self.cfg, "ai_max_age_s", 900))
        if now - last > max_age:
            self.log.warning(
                "Reject: stale AI sentiment (age=%.1fs > %.1fs)", now - last, max_age
            )
            if self.metrics:
                self.metrics.risk_rejections_total.labels(reason="stale_ai").inc()
            return False

        # 2) Orderbook spread guard
        if book:
            bid = float(book.get("bid") or 0.0)
            ask = float(book.get("ask") or 0.0)
            if bid > 0.0 and ask > bid:
                spread = (ask - bid) / ((ask + bid) / 2.0)
                max_spread = float(getattr(self.cfg, "max_spread_pct", 0.001))
                if spread > max_spread:
                    self.log.info("Reject: spread %.5f > max %.5f", spread, max_spread)
                    if self.metrics:
                        self.metrics.risk_rejections_total.labels(
                            reason="spread_cap"
                        ).inc()
                    return False

            min_depth = float(getattr(self.cfg, "min_top_depth", 0.0))
            if min_depth > 0.0:
                bid_sz = float(book.get("bid_size") or 0.0)
                ask_sz = float(book.get("ask_size") or 0.0)
                if bid_sz < min_depth or ask_sz < min_depth:
                    self.log.info(
                        "Reject: shallow book (bid_sz=%.4f, ask_sz=%.4f < %.4f)",
                        bid_sz,
                        ask_sz,
                        min_depth,
                    )
                    if self.metrics:
                        self.metrics.risk_rejections_total.labels(
                            reason="min_depth"
                        ).inc()
                    return False

        # 3) Sentiment gating
        current_sentiment = self.ai_analyzer.get_current_sentiment()
        action = signal.get("action")
        if action == "enter_long" and current_sentiment == "Bearish":
            self.log.warning("Reject: sentiment Bearish for long.")
            if self.metrics:
                self.metrics.risk_rejections_total.labels(reason="ai_sentiment").inc()
            return False
        if action == "enter_short" and current_sentiment == "Bullish":
            self.log.warning("Reject: sentiment Bullish for short.")
            if self.metrics:
                self.metrics.risk_rejections_total.labels(reason="ai_sentiment").inc()
            return False

        # 4) Daily drawdown halt
        start = float(self.starting_budget or 0.0)
        if start > 0.0:
            drawdown_pct = (float(current_budget) - start) / start
            limit = -abs(float(getattr(self.cfg, "daily_drawdown_pct", 0.10)))
            if drawdown_pct <= limit:
                self.trading_paused_drawdown = True
                self.log.error(
                    "Reject: daily drawdown %.2f%% <= limit %.2f%%. Trading paused.",
                    100 * drawdown_pct,
                    100 * limit,
                )
                if self.metrics:
                    self.metrics.risk_rejections_total.labels(
                        reason="drawdown_limit"
                    ).inc()
                return False

        # 5) Dynamic throttling
        if self.trading_paused_throttle:
            self.log.warning("Reject: trading throttled due to low win rate.")
            if self.metrics:
                self.metrics.risk_rejections_total.labels(reason="throttling").inc()
            return False

        if len(self.trade_history) == self.trade_history.maxlen:
            wr = self._win_rate()
            threshold = float(getattr(self.cfg, "throttle_threshold_pct", 0.5))
            if wr is not None and wr < threshold:
                self.trading_paused_throttle = True
                self.log.warning(
                    "Trading paused: win rate %.1f%% < threshold %.1f%%.",
                    100 * wr,
                    100 * threshold,
                )
                if self.metrics:
                    self.metrics.risk_rejections_total.labels(reason="throttling").inc()
                return False

        return True

    def update_trade_history(self, pnl: float) -> None:
        self.trade_history.append(1 if pnl > 0 else 0)
        if self.trading_paused_throttle:
            wr = self._win_rate()
            threshold = float(getattr(self.cfg, "throttle_threshold_pct", 0.5))
            if wr is not None and wr >= threshold:
                self.trading_paused_throttle = False
                self.log.info(
                    "Throttle lifted: win rate %.1f%% >= threshold %.1f%%.",
                    100 * wr,
                    100 * threshold,
                )
