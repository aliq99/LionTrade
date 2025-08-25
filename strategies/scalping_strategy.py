import pandas as pd
import pandas_ta as ta
import logging

class ScalpingStrategy:
    def __init__(self, cfg):
        self.cfg = cfg
        self.candles = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        self.current_candle = None
        self.last_candle_timestamp = None
        self.latest_bid = None
        self.latest_ask = None
        # --- ADDED: Initialize the logger ---
        self.log = logging.getLogger("momo")
        self.log.info("ScalpingStrategy Initialized with TA, Spread tracking, and Logging.")

    def on_tick_update(self, tick_data):
        """Builds 1-minute candles from historical ticks and returns True when a candle is finalized."""
        price = tick_data.get('price')
        timestamp = tick_data.get('timestamp')
        if price is None or timestamp is None:
            return False

        current_candle_ts = timestamp.floor('1min')
        candle_finalized = False

        if self.last_candle_timestamp and self.last_candle_timestamp < current_candle_ts:
            self.candles.loc[self.last_candle_timestamp] = self.current_candle
            if len(self.candles) > 100:
                self.candles.drop(self.candles.index[0], inplace=True)
            self.current_candle = None
            candle_finalized = True

        if self.current_candle is None:
            self.current_candle = {'open': price, 'high': price, 'low': price, 'close': price, 'volume': 0}
            self.last_candle_timestamp = current_candle_ts
        
        self.current_candle['high'] = max(self.current_candle['high'], price)
        self.current_candle['low'] = min(self.current_candle['low'], price)
        self.current_candle['close'] = price
        
        return candle_finalized

    def on_order_book_update(self, order_book):
        """Captures the latest bid and ask."""
        if 'bids' in order_book and order_book['bids']:
            self.latest_bid = float(order_book['bids'][0][0])
        if 'asks' in order_book and order_book['asks']:
            self.latest_ask = float(order_book['asks'][0][0])
    
    def generate_signal(self):
        """Calculates indicators and generates a buy/sell signal if conditions are met."""
        if len(self.candles) < 22:
            return None

        # Calculate Indicators
        self.candles.ta.ema(length=9, append=True, col_names=('EMA_9',))
        self.candles.ta.ema(length=21, append=True, col_names=('EMA_21',))
        self.candles.ta.rsi(length=14, append=True, col_names=('RSI_14',))
        
        last_row = self.candles.iloc[-1]
        prev_row = self.candles.iloc[-2]

        # --- Detailed Logging ---
        self.log.debug(f"Checking signals: Price={last_row['close']:.4f}, RSI={last_row['RSI_14']:.2f}, EMA9={last_row['EMA_9']:.4f}, EMA21={last_row['EMA_21']:.4f}")

        # --- Signal Logic ---
        ema_buy_signal = prev_row['EMA_9'] < prev_row['EMA_21'] and last_row['EMA_9'] > last_row['EMA_21']
        rsi_buy_signal = last_row['RSI_14'] < self.cfg.rsi_oversold
        
        ema_sell_signal = prev_row['EMA_9'] > prev_row['EMA_21'] and last_row['EMA_9'] < last_row['EMA_21']
        rsi_sell_signal = last_row['RSI_14'] > self.cfg.rsi_overbought
        
        # --- Decision Making ---
        if ema_buy_signal or rsi_buy_signal:
            self.log.info(f"TRADE SIGNAL DETECTED: BUY | RSI={last_row['RSI_14']:.2f}, Bullish EMA Cross={ema_buy_signal}")
            return {"action": "enter_long", "price": last_row['close']}
        
        if ema_sell_signal or rsi_sell_signal:
            self.log.info(f"TRADE SIGNAL DETECTED: SELL | RSI={last_row['RSI_14']:.2f}, Bearish EMA Cross={ema_sell_signal}")
            return {"action": "exit", "price": last_row['close']}

        return None
