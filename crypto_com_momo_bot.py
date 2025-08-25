#!/usr/bin/env python3
import os, json, time, asyncio, logging, math, csv, pathlib, datetime as dt
from dataclasses import dataclass
from collections import deque
from dotenv import load_dotenv

# --- All imports are now grouped here at the top ---
from strategies.scalping_strategy import ScalpingStrategy
from strategies.momentum_strategy import MomentumStrategy
from data.websocket_manager import WebSocketManager
from trading.risk_manager import RiskManager
from trading.execution_engine import ExecutionEngine
from trading.ai_analyzer import AI_Analyzer

# ---------- env & logging ----------
load_dotenv()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format="%(asctime)s | %(levelname)s | %(message)s")
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
log = logging.getLogger("momo")

# ---------- Data Handlers for Dashboard ----------
chart_data = deque(maxlen=200)
def save_live_data(trade_event=None):
    output = { "prices": list(chart_data) }
    if trade_event:
        output["trade"] = trade_event
    with open("live_data.json", "w") as f:
        json.dump(output, f)

# ---------- config ----------
def load_config():
    try:
        with open("config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"strategy_name": "momentum", "symbol_ccxt": "BTC/USDT", "total_budget_usdt": 1000.0}
bot_config = load_config()

@dataclass
class Config:
    # --- Execution Settings ---
    execution_mode: str = bot_config.get("execution_mode", "auto")
    large_order_threshold_usdt: float = float(bot_config.get("large_order_threshold_usdt", "500"))
    twap_duration_minutes: int = int(bot_config.get("twap_duration_minutes", "30"))
    twap_order_slices: int = int(bot_config.get("twap_order_slices", "10"))
    
    # --- Risk Management Settings ---
    max_spread_pct: float = float(os.getenv("MAX_SPREAD_PCT", "0.001"))
    throttle_window: int = int(os.getenv("THROTTLE_WINDOW", "20"))
    throttle_threshold_pct: float = float(os.getenv("THROTTLE_THRESHOLD", "0.40"))
    daily_drawdown_pct: float = float(os.getenv("DRAWDOWN_PCT", "0.02"))

    # --- Budget & Position Settings ---
    total_budget_usdt: float = float(bot_config.get("total_budget_usdt", "1000"))
    risk_per_trade_pct: float = float(bot_config.get("risk_per_trade_pct", "0.01"))
    stop_loss_pct: float = float(bot_config.get("stop_loss_pct", "0.004"))
    take_profit_pct: float = float(bot_config.get("take_profit_pct", "0.01"))
    
    # --- Strategy-Specific Settings ---
    ema_len: int = int(os.getenv("EMA_LEN", "12"))
    zscore_len: int = int(os.getenv("ZSCORE_LEN", "20"))
    zscore_entry: float = float(os.getenv("ZSCORE_ENTRY", "0.4"))
    rsi_oversold: float = float(os.getenv("RSI_OVERSOLD", "45"))
    rsi_overbought: float = float(os.getenv("RSI_OVERBOUGHT", "55"))
    
    # --- General Settings ---
    symbol_ccxt: str = bot_config.get("symbol_ccxt", "BTC/USDT")
    ws_url: str = os.getenv("CRYPTOCOM_WS_URL", "wss://stream.crypto.com/exchange/v1/market")
    cooldown_sec: int = int(os.getenv("COOLDOWN_SEC", "10")) # <-- THIS LINE WAS MISSING
    paper: bool = os.getenv("PAPER", "true").lower() == "true"

cfg = Config()

# ---------- paths & csv helpers ----------
BASE_DIR = pathlib.Path(__file__).parent
TRADES_CSV = BASE_DIR / "trades.csv"
def _ensure_trades_header():
    if not TRADES_CSV.exists() or TRADES_CSV.stat().st_size == 0:
        with TRADES_CSV.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(["ts_iso","symbol","action","side","price","qty","reason","pnl_usdt"])
def _log_trade(symbol, action, side, price, qty, reason="", pnl_usdt=""):
    _ensure_trades_header()
    row = [dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), symbol, action, side, f"{price:.8f}", f"{qty:.8f}", reason, f"{pnl_usdt:.8f}" if pnl_usdt else ""]
    with TRADES_CSV.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(row)

# --- Bot Entry Point ---
async def main():
    cfg = Config()
    strategy_name = bot_config.get("strategy_name", "scalping")
    
    active_strategy = ScalpingStrategy(cfg) if strategy_name == "scalping" else MomentumStrategy(cfg)
    log.info(f"Loaded {strategy_name.upper()} strategy.")
    
    # --- Initialize all components, including the AI Analyzer ---
    ai_analyzer = AI_Analyzer()
    risk_manager = RiskManager(cfg, ai_analyzer)
    execution_engine = ExecutionEngine(cfg, active_strategy, _log_trade, risk_manager)
    
    # --- Pass all components to the manager ---
    ws_url = cfg.ws_url 
    manager = WebSocketManager(ws_url, active_strategy, risk_manager, execution_engine, ai_analyzer)
    await manager.connect()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
