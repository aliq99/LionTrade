import logging

from config.settings import Settings
from metrics.telemetry import METRICS, write_budget_status


class ExecutionEngine:
    def __init__(self, cfg: Settings, strat, log_trade_func, risk_manager):
        self.cfg = cfg
        self.strat = strat
        self.log = logging.getLogger("momo")
        self.log_trade = log_trade_func
        self.risk_manager = risk_manager
        self.budget = cfg.total_budget_usdt
        self._open_positions = 0

        METRICS.budget_usdt.set(self.budget)
        METRICS.open_positions.set(0)
        write_budget_status(self.budget, 0)

        self.log.info(
            f"ExecutionEngine Initialized with budget: ${self.budget:,.2f} USDT"
        )

    def _order_size(self, price: float) -> float:
        if price is None or price <= 0:
            return 0.0
        notional_to_risk = self.budget * self.cfg.risk_per_trade_pct
        return max(notional_to_risk / price, 0.0)

    def act(self, decision: dict):
        if not decision:
            return

        action = decision.get("action")

        # -------- EXIT FIRST --------
        if action == "exit":
            if not getattr(self.strat, "pos", None):
                return

            exit_price = getattr(self.strat, "latest_ask", decision.get("price"))
            if exit_price is None or exit_price <= 0:
                return

            entry = float(self.strat.pos.get("entry", 0))
            qty = float(self.strat.pos.get("qty", 0))
            if entry <= 0 or qty <= 0:
                self.strat.pos = None
                return

            pnl = (exit_price - entry) * qty
            self.budget += pnl
            self.risk_manager.update_trade_history(pnl)

            reason = decision.get("reason", "")
            self.log.info(
                f"[PAPER] EXIT {self.strat.pos['side']} @ {exit_price:.8f} ({reason}) | PnL={pnl:.2f} | New Budget=${self.budget:,.2f}"
            )
            self.log_trade(
                self.cfg.symbol_ccxt,
                "EXIT",
                self.strat.pos["side"],
                exit_price,
                qty,
                reason=reason,
                pnl_usdt=pnl,
            )

            self.strat.pos = None
            METRICS.trades_exited_total.inc()
            METRICS.budget_usdt.set(self.budget)
            self._open_positions = max(0, self._open_positions - 1)
            METRICS.open_positions.set(self._open_positions)
            write_budget_status(self.budget, self._open_positions)
            return

        # -------- ENTRIES --------
        if action == "enter_long":
            if getattr(self.strat, "pos", None):
                return

            price = getattr(self.strat, "latest_bid", decision.get("price"))
            if price is None or price <= 0:
                return

            qty = self._order_size(price)
            if qty <= 0:
                return

            notional_value = qty * price
            mode = str(self.cfg.execution_mode).lower()

            if (
                mode == "auto"
                and notional_value > float(self.cfg.large_order_threshold_usdt)
            ) or mode == "twap":
                reason = "twap_entry"
            else:
                reason = "smart_limit_entry"

            entry_price = price
            self.log.info(f"[PAPER] BUY {qty:.6f} @ {entry_price:.8f}")
            self.log_trade(
                self.cfg.symbol_ccxt,
                "ENTER",
                "LONG",
                entry_price,
                qty,
                reason=reason,
                pnl_usdt=None,
            )

            self.strat.pos = {"side": "LONG", "qty": qty, "entry": entry_price}
            METRICS.trades_entered_total.inc()
            self._open_positions += 1
            METRICS.open_positions.set(self._open_positions)
            write_budget_status(self.budget, self._open_positions)
            return
