import pandas as pd
from tqdm import tqdm

# --- Import all the new, modular components ---
from crypto_com_momo_bot import Config, _log_trade, load_config
from strategies.momentum_strategy import MomentumStrategy
from strategies.scalping_strategy import ScalpingStrategy
from trading.risk_manager import RiskManager
from trading.execution_engine import ExecutionEngine

class MockAIAnalyzer:
    """A fake AI analyzer for backtesting under specific sentiment scenarios."""
    def __init__(self, mock_sentiment="Bullish"):
        self.sentiment = mock_sentiment
        print(f"MockAIAnalyzer Initialized. Simulating '{self.sentiment}' sentiment.")

    def get_current_sentiment(self):
        return self.sentiment

def analyze_results(engine: ExecutionEngine, trades_file="trades.csv"):
    """Reads trades.csv and the final engine state for a performance report."""
    starting_budget = engine.cfg.total_budget_usdt
    ending_budget = engine.budget
    
    try:
        df = pd.read_csv(trades_file)
        exits = df[df['action'] == 'EXIT'].copy()
        if exits.empty:
            print("\n--- No trades were exited during the backtest. ---")
            return

        total_trades = len(exits)
        wins = (exits['pnl_usdt'] > 0).sum()
        win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
        net_pnl = ending_budget - starting_budget
        percent_return = (net_pnl / starting_budget) * 100

        print("\n--- Final Performance Report ---")
        print(f"Starting Budget: ${starting_budget:,.2f} USDT")
        print(f"Ending Budget:   ${ending_budget:,.2f} USDT")
        print(f"Net PnL:         ${net_pnl:,.2f} USDT ({percent_return:.2f}%)")
        print(f"Total Trades:    {total_trades}")
        print(f"Win Rate:        {win_rate:.2f}%")
        print("--------------------------------")
        
    except FileNotFoundError:
        print("No trades.csv file found to analyze.")

def run_backtest(files_to_test, strategy, risk_manager, execution_engine):
    """Processes a list of data files against the given components."""
    for data_file in files_to_test:
        print(f"\n--- Processing file: {data_file} ---")
        
        column_names = ['trade_id', 'price', 'qty', 'quote_qty', 'timestamp', 'is_buyer_maker', 'is_best_match']
        df = pd.read_csv(data_file, header=None, names=column_names)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        print(f"Loaded {len(df)} rows of data.")

        for index, row in tqdm(df.iterrows(), total=df.shape[0]):
            price = row['price']
            timestamp = row['timestamp']
            
            signal = None
            if isinstance(strategy, MomentumStrategy):
                signal = strategy.on_price(price)
            elif isinstance(strategy, ScalpingStrategy):
                strategy.on_order_book_update({'bids': [[price, 1]], 'asks': [[price * 1.0001, 1]]})
                candle_finalized = strategy.on_tick_update({'price': price, 'timestamp': timestamp})
                if candle_finalized:
                    signal = strategy.generate_signal()
            
            if signal:
                if risk_manager.approve_trade(signal, execution_engine.budget):
                    execution_engine.act(signal)

if __name__ == "__main__":
    SENTIMENT_SCENARIO = "Bullish"
    
    bot_config = load_config()
    cfg = Config()
    strategy_name = bot_config.get("strategy_name", "scalping")

    active_strategy = ScalpingStrategy(cfg) if strategy_name == "scalping" else MomentumStrategy(cfg)
    mock_ai_analyzer = MockAIAnalyzer(mock_sentiment=SENTIMENT_SCENARIO)
    risk_manager = RiskManager(cfg, mock_ai_analyzer)
    execution_engine = ExecutionEngine(cfg, active_strategy, _log_trade, risk_manager)
    print(f"--- Starting Backtest for {strategy_name.upper()} Strategy ---")

    historical_files = [
        "BTSUSDT-trades-2023-10.csv",
        "BTSUSDT-trades-2023-11.csv",
        "BTSUSDT-trades-2023-12.csv",
    ]
    
    run_backtest(historical_files, active_strategy, risk_manager, execution_engine)
    print("\n--- Backtest Complete ---")
    analyze_results(execution_engine)
