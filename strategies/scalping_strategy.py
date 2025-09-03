import logging

import pandas as pd

from indicators.rolling import RollingEMA, RollingRSI


class ScalpingStrategy:
    def __init__(self, cfg, metrics=None):
        self.cfg = cfg
        self.metrics = metrics
        self.log = logging.getLogger("momo")
        self.log.info("ScalpingStrategy initialized.")

        # Indicator setup
        fast_len = int(getattr(cfg, "ema_fast_len", 9))
        slow_len = int(getattr(cfg, "ema_slow_len", 21))
        rsi_len = int(getattr(cfg, "rsi_len", 14))

        self.ema_fast = RollingEMA(fast_len)
        self.ema_slow = RollingEMA(slow_len)
        self.rsi = RollingRSI(rsi_len)

        # Configuration thresholds
        self.rsi_oversold = float(getattr(cfg, "rsi_oversold", 30))
        self.rsi_overbought = float(getattr(cfg, "rsi_overbought", 70))

        # Candle and state tracking
        self.candles = pd.DataFrame(
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        self.current_candle = None
        self.last_candle_timestamp = None
        self.latest_bid = None
        self.latest_ask = None
        self.pos = None

        # Track indicator values for signal generation
        self.last_ema_fast = None
        self.last_ema_slow = None
        self.prev_ema_fast = None
        self.prev_ema_slow = None
        self.current_rsi = None

    def on_tick_update(self, tick_data: dict) -> bool:
        """Builds 1-minute candles from ticks and returns True when a candle is finalized."""
        price = tick_data.get("price")
        timestamp = tick_data.get("timestamp")

        if price is None or timestamp is None:
            return False

        # Use the timestamp from tick data (historical for backtesting, real-time for live)
        current_candle_ts = timestamp.floor("1min")
        candle_finalized = False

        # Check if we need to finalize the previous candle
        if (
            self.last_candle_timestamp
            and self.last_candle_timestamp < current_candle_ts
        ):
            if self.current_candle is not None:
                # Finalize the candle
                candle_data = {
                    "timestamp": self.last_candle_timestamp,
                    "open": self.current_candle["open"],
                    "high": self.current_candle["high"],
                    "low": self.current_candle["low"],
                    "close": self.current_candle["close"],
                    "volume": self.current_candle["volume"],
                }

                # Add to candles DataFrame
                self.candles = pd.concat(
                    [self.candles, pd.DataFrame([candle_data])], ignore_index=True
                )

                # Update indicators with the finalized candle's close price
                close_price = self.current_candle["close"]

                # Store previous EMA values for crossover detection
                self.prev_ema_fast = self.last_ema_fast
                self.prev_ema_slow = self.last_ema_slow

                # Update indicators
                self.last_ema_fast = self.ema_fast.update(close_price)
                self.last_ema_slow = self.ema_slow.update(close_price)
                self.current_rsi = self.rsi.update(close_price)

                # Keep only recent candles to prevent memory issues
                if len(self.candles) > 200:
                    self.candles = self.candles.tail(100).reset_index(drop=True)

                candle_finalized = True
                self.log.debug(
                    f"Candle finalized at {self.last_candle_timestamp}: OHLC({self.current_candle['open']:.4f}, {self.current_candle['high']:.4f}, {self.current_candle['low']:.4f}, {self.current_candle['close']:.4f})"
                )

        # Start new candle or update current one
        if (
            self.current_candle is None
            or self.last_candle_timestamp != current_candle_ts
        ):
            self.current_candle = {
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 1,
            }
            self.last_candle_timestamp = current_candle_ts
        else:
            # Update current candle
            self.current_candle["high"] = max(self.current_candle["high"], price)
            self.current_candle["low"] = min(self.current_candle["low"], price)
            self.current_candle["close"] = price
            self.current_candle["volume"] += 1

        return candle_finalized

    def generate_signal(self):
        """Analyzes completed candles and returns a signal if conditions are met."""
        # Need enough data for indicators
        min_periods_needed = max(
            int(getattr(self.cfg, "ema_slow_len", 21)),
            int(getattr(self.cfg, "rsi_len", 14)),
        )

        if len(self.candles) < min_periods_needed:
            self.log.debug(
                f"Not enough candles yet: {len(self.candles)}/{min_periods_needed}"
            )
            return None

        # Need both current and previous EMA values for crossover detection
        if (
            self.last_ema_fast is None
            or self.last_ema_slow is None
            or self.prev_ema_fast is None
            or self.prev_ema_slow is None
        ):
            self.log.debug("EMA values not ready for crossover detection")
            return None

        if self.current_rsi is None:
            self.log.debug("RSI not ready")
            return None

        # Check for EMA crossover signals
        crossed_up = (
            self.prev_ema_fast <= self.prev_ema_slow
            and self.last_ema_fast > self.last_ema_slow
        )
        crossed_down = (
            self.prev_ema_fast >= self.prev_ema_slow
            and self.last_ema_fast < self.last_ema_slow
        )

        # Check RSI conditions
        rsi_oversold = self.current_rsi < self.rsi_oversold
        rsi_overbought = self.current_rsi > self.rsi_overbought

        current_price = (
            self.candles.iloc[-1]["close"]
            if len(self.candles) > 0
            else self.current_candle["close"]
        )

        self.log.debug(
            f"Signal check - EMA Fast: {self.last_ema_fast:.4f}, EMA Slow: {self.last_ema_slow:.4f}, RSI: {self.current_rsi:.2f}"
        )
        self.log.debug(
            f"Crossed up: {crossed_up}, Crossed down: {crossed_down}, RSI oversold: {rsi_oversold}, RSI overbought: {rsi_overbought}"
        )

        # Generate buy signals
        if crossed_up or rsi_oversold:
            if self.metrics:
                self.metrics.signals_total.labels(
                    action="enter_long", strategy="scalping"
                ).inc()
            self.log.info(
                f"BUY signal generated - EMA crossed up: {crossed_up}, RSI oversold: {rsi_oversold} (RSI: {self.current_rsi:.2f})"
            )
            return {"action": "enter_long", "price": current_price}

        # Generate sell signals
        if crossed_down or rsi_overbought:
            if self.metrics:
                self.metrics.signals_total.labels(
                    action="exit", strategy="scalping"
                ).inc()
            self.log.info(
                f"SELL signal generated - EMA crossed down: {crossed_down}, RSI overbought: {rsi_overbought} (RSI: {self.current_rsi:.2f})"
            )
            return {"action": "exit", "price": current_price}

        return None

    def on_order_book_update(self, order_book: dict):
        """Update latest bid/ask prices from order book."""
        try:
            if "bids" in order_book and order_book["bids"]:
                self.latest_bid = float(order_book["bids"][0][0])
            elif "bid" in order_book:
                self.latest_bid = float(order_book["bid"])

            if "asks" in order_book and order_book["asks"]:
                self.latest_ask = float(order_book["asks"][0][0])
            elif "ask" in order_book:
                self.latest_ask = float(order_book["ask"])
        except (ValueError, IndexError, KeyError) as e:
            self.log.warning(f"Error updating order book: {e}")

    def get_status(self):
        """Return current strategy status for debugging."""
        return {
            "candles_count": len(self.candles),
            "current_candle": self.current_candle,
            "last_ema_fast": self.last_ema_fast,
            "last_ema_slow": self.last_ema_slow,
            "current_rsi": self.current_rsi,
            "latest_bid": self.latest_bid,
            "latest_ask": self.latest_ask,
        }
