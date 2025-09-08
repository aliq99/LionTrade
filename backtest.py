import logging
import os
import sqlite3
import time
from datetime import datetime, timezone

import pandas as pd
from tqdm import tqdm

from config.settings import load_settings
from persistence.trades_db import init_db, insert_trade
from strategies.momentum_strategy import MomentumStrategy
from strategies.scalping_strategy import ScalpingStrategy
from trading.execution_engine import ExecutionEngine
from trading.risk_manager import RiskManager

# ---- config ----
cfg = load_settings()
logging.basicConfig(level=logging.INFO)


# ---- trade logger used by ExecutionEngine ----
def _log_trade(symbol, action, side, price, qty, reason="", pnl_usdt=None):
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    insert_trade(
        ts,
        symbol,
        action,  # "ENTER" or "EXIT"
        side,  # "LONG"/"SHORT" or "BUY"/"SELL"
        float(price or 0),
        float(qty or 0),
        reason or "",
        pnl_usdt,
    )


# ---- mock AI for backtests ----
class MockAIAnalyzer:
    def __init__(self, mock_sentiment="Bullish"):
        self.sentiment = mock_sentiment
        self.last_analysis_time = time.time()
        print(f"MockAIAnalyzer Initialized. Simulating '{self.sentiment}' sentiment.")

    def get_current_sentiment(self):
        return self.sentiment

    def refresh_sentiment(self, *_args, **_kwargs):
        self.last_analysis_time = time.time()


# ---- reporting ----
def analyze_results(engine: ExecutionEngine):
    starting_budget = engine.cfg.total_budget_usdt
    ending_budget = engine.budget
    net_pnl = ending_budget - starting_budget
    percent_return = (net_pnl / starting_budget) * 100 if starting_budget > 0 else 0

    total_trades, win_rate = 0, 0.0
    try:
        db_path = "persistence/trades.db"
        if os.path.exists(db_path):
            con = sqlite3.connect(db_path)
            exits_df = pd.read_sql_query(
                "SELECT pnl_usdt FROM trades WHERE action = 'EXIT'", con
            )
            con.close()
            if not exits_df.empty:
                total_trades = len(exits_df)
                winning_trades = (exits_df["pnl_usdt"] > 0).sum()
                win_rate = (
                    (winning_trades / total_trades * 100) if total_trades > 0 else 0
                )
    except Exception as e:
        print(f"Could not analyze trades from DB: {e}")

    print("\n--- Final Performance Report ---")
    print(f"Starting Budget: ${starting_budget:,.2f} USDT")
    print(f"Ending Budget:   ${ending_budget:,.2f} USDT")
    print(f"Net PnL:         ${net_pnl:,.2f} USDT ({percent_return:.2f}%)")
    print(f"Total Trades:    {total_trades}")
    print(f"Win Rate:        {win_rate:.2f}%")
    print("--------------------------------")


# ---- data loading ----
def load_and_validate_data(data_file: str):
    cols = [
        "trade_id",
        "price",
        "qty",
        "quote_qty",
        "timestamp",
        "is_buyer_maker",
        "is_best_match",
    ]

    if not os.path.exists(data_file):
        print(f"ERROR: Data file not found: {data_file}")
        return None

    try:
        df = pd.read_csv(data_file, header=None, names=cols)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.sort_values("timestamp").reset_index(drop=True)
        print(f"Loaded {len(df)} rows from {data_file}")
        print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        return df
    except Exception as e:
        print(f"ERROR loading {data_file}: {e}")
        return None


# ---- backtest loop ----
def run_backtest(files_to_test, strategy, risk_manager, execution_engine):
    total_signals = 0
    total_approved_trades = 0

    for data_file in files_to_test:
        print(f"\n--- Processing file: {data_file} ---")
        df = load_and_validate_data(data_file)
        if df is None:
            continue

        file_signals = 0
        file_trades = 0

        for _idx, row in tqdm(
            df.iterrows(), total=df.shape[0], desc=f"Processing {data_file}"
        ):
            price = float(row["price"])
            ts = row["timestamp"]  # pandas.Timestamp (UTC)

            # Build a rich mock book for both strategy & risk gates
            mock_book = {
                # for RiskManager
                "bid": price * 0.9999,
                "ask": price * 1.0001,
                "bid_size": 1_000_000.0,
                "ask_size": 1_000_000.0,
                # for strategy order-book updater (bids/asks arrays)
                "bids": [[price * 0.9999, 1_000_000.0]],
                "asks": [[price * 1.0001, 1_000_000.0]],
            }

            signal = None

            if isinstance(strategy, ScalpingStrategy):
                # keep strategy's best bid/ask in sync
                strategy.on_order_book_update(mock_book)

                # "time travel" safe tick: pass price + historical timestamp
                candle_finalized = strategy.on_tick_update(
                    {"price": price, "timestamp": ts}
                )

                if candle_finalized and hasattr(strategy, "generate_signal"):
                    signal = strategy.generate_signal()
                    if signal:
                        file_signals += 1
                        total_signals += 1
                        print(f"Signal generated at {ts}: {signal}")

            elif isinstance(strategy, MomentumStrategy):
                # If your MomentumStrategy has a similar API, adapt here
                pass

            if signal:
                # use historical epoch seconds for now_ts
                now_epoch = float(ts.timestamp())
                if risk_manager.approve_trade(
                    signal, execution_engine.budget, book=mock_book, now_ts=now_epoch
                ):
                    execution_engine.act(signal)
                    file_trades += 1
                    total_approved_trades += 1
                    print(
                        f"Trade executed: {signal['action']} at ${signal['price']:.6f}"
                    )
                else:
                    print(f"Trade rejected by risk manager: {signal}")

        print(f"File summary - Signals: {file_signals}, Trades: {file_trades}")
        if hasattr(strategy, "get_status"):
            print(f"Strategy status: {strategy.get_status()}")

    print("\nBacktest Summary:")
    print(f"Total signals generated: {total_signals}")
    print(f"Total trades approved:   {total_approved_trades}")


# ---- main ----
def main():
    # reset DB
    try:
        db_path = "persistence/trades.db"
        if os.path.exists(db_path):
            os.remove(db_path)
        init_db()
        print("Database reset successfully.")
    except Exception as e:
        print(f"Could not reset database: {e}")

    SENTIMENT_SCENARIO = "Bullish"

    # pick strategy
    strategy_name = cfg.strategy_name
    if strategy_name == "scalping":
        active_strategy = ScalpingStrategy(cfg)  # <- single-arg ctor
    else:
        active_strategy = MomentumStrategy(cfg)  # <- single-arg ctor

    # wire components
    mock_ai_analyzer = MockAIAnalyzer(mock_sentiment=SENTIMENT_SCENARIO)
    risk_manager = RiskManager(cfg, mock_ai_analyzer)  # only (cfg, ai_analyzer)
    execution_engine = ExecutionEngine(cfg, active_strategy, _log_trade, risk_manager)

    print(f"--- Starting Backtest for {strategy_name.upper()} Strategy ---")
    print("Configuration:")
    print(f"  - EMA Fast Length: {getattr(cfg, 'ema_fast_len', 9)}")
    print(f"  - EMA Slow Length: {getattr(cfg, 'ema_slow_len', 21)}")
    print(f"  - RSI Length:      {getattr(cfg, 'rsi_len', 14)}")
    print(f"  - RSI Oversold:    {getattr(cfg, 'rsi_oversold', 30)}")
    print(f"  - RSI Overbought:  {getattr(cfg, 'rsi_overbought', 70)}")
    print(f"  - Total Budget:    ${cfg.total_budget_usdt}")

    historical_files = [
        "BTSUSDT-trades-2023-10.csv",
        "BTSUSDT-trades-2023-11.csv",
        "BTSUSDT-trades-2023-12.csv",
    ]

    run_backtest(historical_files, active_strategy, risk_manager, execution_engine)
    print("\n--- Backtest Complete ---")
    analyze_results(execution_engine)


if __name__ == "__main__":
    main()
