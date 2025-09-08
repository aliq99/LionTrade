#!/usr/bin/env python3
import asyncio
import datetime as dt
import json
import logging
from collections import deque

from dotenv import load_dotenv

from config.settings import cfg
from data.websocket_manager import WebSocketManager
from metrics.telemetry import METRICS, start_metrics_server
from persistence.trades_db import init_db, insert_trade
from strategies.momentum_strategy import MomentumStrategy
from strategies.scalping_strategy import ScalpingStrategy
from trading.ai_analyzer import AI_Analyzer
from trading.execution_engine import ExecutionEngine
from trading.risk_manager import RiskManager

# --- Environment and Logging Setup ---
load_dotenv()
LOG_LEVEL = cfg.log_level.upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("asyncio").setLevel(logging.WARNING)
log = logging.getLogger("momo")

WS_URL = cfg.ws_url  # single authoritative source for websocket URL

# --- Helper Functions ---
chart_data = deque(maxlen=200)


def save_live_data(trade_event=None):
    """Save recent prices and optional trade event to a JSON file for the dashboard."""
    output = {"prices": list(chart_data)}
    if trade_event:
        output["trade"] = trade_event
    try:
        with open("live_data.json", "w", encoding="utf-8") as f:
            json.dump(output, f)
    except Exception as e:
        log.error("Error saving live_data.json: %s", e)


def _log_trade(symbol, action, side, price, qty, reason="", pnl_usdt=None):
    """Adapter to log a trade to the SQLite database."""
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    insert_trade(ts, symbol, action, side, price, qty, reason, pnl_usdt)


async def _ai_refresh_loop(ai_analyzer: AI_Analyzer):
    """Background task to refresh AI sentiment periodically."""
    while True:
        try:
            ai_analyzer.refresh_sentiment()
        except Exception as e:
            log.error("AI refresh error: %s", e)
        await asyncio.sleep(max(60, ai_analyzer.cache_duration))


# --- Main Bot Entry Point ---
async def main():
    init_db()
    start_metrics_server(cfg.metrics_port)
    log.info("Metrics server listening on :%d", cfg.metrics_port)

    strategy_name = cfg.strategy_name
    active_strategy = (
        ScalpingStrategy(cfg, METRICS)
        if strategy_name == "scalping"
        else MomentumStrategy(cfg, METRICS)
    )
    log.info("Loaded %s strategy.", strategy_name.upper())

    ai_analyzer = AI_Analyzer()
    asyncio.create_task(_ai_refresh_loop(ai_analyzer))

    risk_manager = RiskManager(cfg, ai_analyzer, METRICS)
    execution_engine = ExecutionEngine(cfg, active_strategy, _log_trade, risk_manager)
    risk_manager.start_day(execution_engine.budget)

    manager = WebSocketManager(
        WS_URL,
        active_strategy,
        risk_manager,
        execution_engine,
        ai_analyzer,
        save_live_data,
    )
    await manager.connect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
