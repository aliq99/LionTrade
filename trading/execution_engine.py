import math
import logging
# No asyncio import is needed here anymore

class ExecutionEngine:
    def __init__(self, cfg, strat, log_trade_func, risk_manager):
        self.cfg = cfg
        self.strat = strat
        self.log = logging.getLogger("momo") 
        self.log_trade = log_trade_func
        self.risk_manager = risk_manager
        self.budget = self.cfg.total_budget_usdt
        self.log.info(f"ExecutionEngine Initialized with budget: ${self.budget:,.2f} USDT")

    def _order_size(self, price):
        if price is None or price <= 0: return 0.0
        notional_to_risk = self.budget * self.cfg.risk_per_trade_pct
        return max(notional_to_risk / price, 0.0)

    def act(self, decision):
        """
        A unified, synchronous method to handle all trade execution logic.
        """
        if not decision: return

        # --- Handle Exits First ---
        if decision["action"] == "exit":
            if not getattr(self.strat, 'pos', None): return
            
            exit_price = getattr(self.strat, 'latest_ask', decision.get('price'))
            if exit_price is None: return

            entry = float(self.strat.pos.get("entry", 0) or 0)
            qty = float(self.strat.pos.get("qty", 0) or 0)
            if entry <= 0 or qty <= 0:
                self.strat.pos = None
                return
            pnl = (exit_price - entry) * qty
            self.budget += pnl
            self.risk_manager.update_trade_history(pnl)
            self.log.info(f"[PAPER] EXIT {self.strat.pos['side']} @ {exit_price} ({decision.get('reason','')}) | PnL={pnl:.2f} | New Budget=${self.budget:,.2f}")
            self.log_trade(self.cfg.symbol_ccxt, "EXIT", self.strat.pos['side'], exit_price, qty, reason=decision.get('reason',''), pnl_usdt=pnl)
            self.strat.pos = None
            return

        # --- Handle Entries ---
        if decision["action"] == "enter_long":
            if getattr(self.strat, 'pos', None): return
            
            # Estimate notional value
            price = getattr(self.strat, 'latest_bid', decision.get('price'))
            if price is None: return
            qty = self._order_size(price)
            notional_value = qty * price

            mode = self.cfg.execution_mode.lower()

            # --- Auto-Selection Logic ---
            # For the backtester, TWAP and Limit orders are simulated the same way,
            # but we can log which path was chosen.
            if mode == 'auto' and notional_value > self.cfg.large_order_threshold_usdt or mode == 'twap':
                self.log.info(f"TWAP execution chosen for order of ${notional_value:,.0f}.")
                # In a backtest, a TWAP is simulated instantly at the entry price
                entry_price = price
                reason = "twap_entry"
            else: # Default to Smart Limit
                self.log.info(f"Smart Limit execution chosen for order of ${notional_value:,.0f}.")
                entry_price = price
                reason = "smart_limit_entry"

            if qty <= 0: return
            self.log.info(f"[PAPER] BUY {qty:.4f} @ {entry_price}")
            self.log_trade(self.cfg.symbol_ccxt, "ENTER", "LONG", entry_price, qty, reason=reason)
            self.strat.pos = {"side": "LONG", "qty": qty, "entry": entry_price}
