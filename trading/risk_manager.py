# In trading/risk_manager.py
from collections import deque

class RiskManager:
    def __init__(self, cfg, ai_analyzer):
        self.cfg = cfg
        self.ai_analyzer = ai_analyzer # NEW: Store reference to the AI analyzer
        # ... (rest of __init__ is the same)
        self.starting_budget = cfg.total_budget_usdt
        self.trading_paused_drawdown = False
        self.trade_history = deque(maxlen=cfg.throttle_window)
        self.trading_paused_throttle = False
        print("RiskManager Initialized with AI Sentiment Filter.")

    def approve_trade(self, signal, current_budget):
        """Checks signal against all risk rules, including AI sentiment."""
        current_sentiment = self.ai_analyzer.get_current_sentiment()
        self.log.debug(f"RiskManager checking signal. AI Sentiment is '{current_sentiment}'.")

        if signal.get('action') == 'enter_long' and current_sentiment == "Bearish":
            self.log.warning(f"Trade REJECTED by RiskManager: AI sentiment is Bearish.")
            return False

        drawdown_pct = (current_budget - self.starting_budget) / self.starting_budget
        if drawdown_pct < -self.cfg.daily_drawdown_pct:
            self.trading_paused_drawdown = True
            print(f"!!! CRITICAL: DAILY DRAWDOWN LIMIT OF {self.cfg.daily_drawdown_pct:.1%} HIT !!!")
            return False
        
        # --- NEW: Check 2: Dynamic Throttling ---
        if self.trading_paused_throttle:
            print("Trade REJECTED: Throttled due to low win rate.")
            return False

        if len(self.trade_history) == self.cfg.throttle_window:
            win_rate = sum(self.trade_history) / len(self.trade_history)
            if win_rate < self.cfg.throttle_threshold_pct:
                self.trading_paused_throttle = True
                print(f"!!! WARNING: WIN RATE ({win_rate:.1%}) BELOW THRESHOLD. TRADING PAUSED. !!!")
                return False
        
        return True
        
    def update_trade_history(self, pnl):
        """Adds the result of a closed trade to the history for throttling checks."""
        self.trade_history.append(1 if pnl > 0 else 0)
        # If performance improves, un-pause trading
        if self.trading_paused_throttle:
             win_rate = sum(self.trade_history) / len(self.trade_history)
             if win_rate >= self.cfg.throttle_threshold_pct:
                 self.trading_paused_throttle = False
                 print("--- PERFORMANCE IMPROVED. DYNAMIC THROTTLE LIFTED. ---")
