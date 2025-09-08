import json
import pathlib
import sqlite3
import subprocess
import sys
import time
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import psutil
import streamlit as st

# --- Initialize Session State ---
if "bot_process" not in st.session_state:
    st.session_state.bot_process = None
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = datetime.now()
if "refresh_count" not in st.session_state:
    st.session_state.refresh_count = 0

# --- Page and File Setup ---
st.set_page_config(
    page_title="AI Trading Bot Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="ðŸ¤–",
)

BASE_DIR = pathlib.Path(__file__).parent
if sys.platform == "win32":
    PYTHON_EXECUTABLE = BASE_DIR / "venv" / "Scripts" / "python.exe"
else:
    PYTHON_EXECUTABLE = BASE_DIR / "venv" / "bin" / "python"
BOT_SCRIPT_PATH = BASE_DIR / "crypto_com_momo_bot.py"
DB_PATH = BASE_DIR / "persistence" / "trades.db"
CONFIG_JSON = BASE_DIR / "config.json"
LIVE_DATA_JSON = BASE_DIR / "live_data.json"
AI_STATUS_JSON = BASE_DIR / "ai_status.json"


# --- Helper Functions ---
@st.cache_data(ttl=10)
def read_trades_from_sqlite():
    """Reads the trades table from the SQLite database with enhanced error handling."""
    cols = ["ts_iso", "symbol", "action", "side", "price", "qty", "reason", "pnl_usdt"]
    if not DB_PATH.exists():
        return pd.DataFrame(columns=cols)
    try:
        with sqlite3.connect(str(DB_PATH)) as con:
            cursor = con.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trades'"
            )
            if not cursor.fetchone():
                return pd.DataFrame(columns=cols)

            query = f"SELECT {', '.join(cols)} FROM trades ORDER BY ts_iso ASC"
            df = pd.read_sql_query(query, con)
            df["ts_iso"] = pd.to_datetime(df["ts_iso"], errors="coerce")
            for col in ["price", "qty", "pnl_usdt"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
    except Exception as e:
        st.error(f"Error reading trades database: {e}")
        return pd.DataFrame(columns=cols)


def load_live_data():
    if LIVE_DATA_JSON.exists():
        try:
            with open(LIVE_DATA_JSON, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def load_ai_status():
    if AI_STATUS_JSON.exists():
        try:
            with open(AI_STATUS_JSON, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def load_config():
    if CONFIG_JSON.exists():
        with open(CONFIG_JSON, "r") as f:
            return json.load(f)
    return {}


def save_config(config):
    with open(CONFIG_JSON, "w") as f:
        json.dump(config, f, indent=4)


def is_bot_running():
    if st.session_state.bot_process:
        try:
            p = psutil.Process(st.session_state.bot_process.pid)
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    st.session_state.bot_process = None
    return False


def get_bot_info():
    if not is_bot_running():
        return {"running": False}
    try:
        p = psutil.Process(st.session_state.bot_process.pid)
        return {
            "running": True,
            "pid": p.pid,
            "cpu_percent": p.cpu_percent(),
            "memory_mb": p.memory_info().rss / (1024 * 1024),
            "create_time": datetime.fromtimestamp(p.create_time()),
            "status": p.status(),
        }
    except Exception:
        return {"running": False}


def start_bot():
    if is_bot_running():
        return False, "Bot is already running."
    try:
        st.session_state.bot_process = subprocess.Popen(
            [str(PYTHON_EXECUTABLE), str(BOT_SCRIPT_PATH)]
        )
        return True, f"Bot started! (PID: {st.session_state.bot_process.pid})"
    except Exception as e:
        return False, f"Failed to start bot: {e}"


def stop_bot():
    if not is_bot_running():
        return False, "Bot is not running."
    try:
        p = psutil.Process(st.session_state.bot_process.pid)
        p.terminate()
        st.session_state.bot_process = None
        return True, "Bot stopped successfully."
    except Exception as e:
        return False, f"Error stopping bot: {e}"


# --- Sidebar ---
with st.sidebar:
    st.header("âš™ï¸ Bot Controls")
    existing_config = load_config()
    strategy_options = ["Momentum", "Scalping"]
    default_strategy_name = existing_config.get("strategy_name", "scalping").title()
    strategy_choice = st.selectbox(
        "Choose Strategy",
        strategy_options,
        index=(
            strategy_options.index(default_strategy_name)
            if default_strategy_name in strategy_options
            else 0
        ),
    )
    symbol = st.text_input(
        "Symbol", value=existing_config.get("symbol_ccxt", "BTC/USDT")
    )
    total_budget = st.number_input(
        "Total Budget (USDT)",
        min_value=1.0,
        value=float(existing_config.get("total_budget_usdt", 1000.0)),
        step=100.0,
    )
    if strategy_choice == "Scalping":
        st.subheader("Scalping Settings")
        risk_per_trade_pct = st.slider(
            "Risk Per Trade (%)",
            0.1,
            25.0,
            float(existing_config.get("risk_per_trade_pct", 1.0)) * 100,
            0.1,
            key="scalping_risk",
        )
        sl_pct = st.slider(
            "Stop Loss (%)",
            0.1,
            5.0,
            float(existing_config.get("stop_loss_pct", 0.5)) * 100,
            0.1,
            key="scalping_sl",
        )
        tp_pct = st.slider(
            "Take Profit (%)",
            0.1,
            5.0,
            float(existing_config.get("take_profit_pct", 0.5)) * 100,
            0.1,
            key="scalping_tp",
        )
        rsi_oversold = st.slider(
            "RSI Oversold Level",
            5,
            45,
            int(existing_config.get("rsi_oversold", 30)),
            key="scalping_rsi_os",
        )
        rsi_overbought = st.slider(
            "RSI Overbought Level",
            55,
            95,
            int(existing_config.get("rsi_overbought", 70)),
            key="scalping_rsi_ob",
        )

    if st.button("ðŸ’¾ Save Settings", type="primary", use_container_width=True):
        new_config = {
            "strategy_name": strategy_choice.lower(),
            "symbol_ccxt": symbol,
            "total_budget_usdt": total_budget,
            "last_updated": datetime.now().isoformat(),
        }
        if strategy_choice == "Scalping":
            new_config.update(
                {
                    "risk_per_trade_pct": risk_per_trade_pct / 100,
                    "stop_loss_pct": sl_pct / 100,
                    "take_profit_pct": tp_pct / 100,
                    "rsi_oversold": rsi_oversold,
                    "rsi_overbought": rsi_overbought,
                }
            )
        save_config(new_config)
        st.sidebar.success(f"âœ… {strategy_choice} settings saved!")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("â–¶ï¸ Start Bot", use_container_width=True):
            success, message = start_bot()
            if success:
                st.success(message)
                time.sleep(1)
                st.rerun()
            else:
                st.error(message)
    with col2:
        if st.button("â¹ï¸ Stop Bot", use_container_width=True):
            success, message = stop_bot()
            if success:
                st.success(message)
                time.sleep(1)
                st.rerun()
            else:
                st.warning(message)
    st.divider()
    st.subheader("ðŸ¤– Bot Status")
    bot_info = get_bot_info()
    if bot_info["running"]:
        st.success(f"âœ… Running (PID: {bot_info['pid']})")
    else:
        st.info("âšª Stopped")
    auto_refresh = st.checkbox("Enable Auto-Refresh", value=True)
    refresh_interval = st.slider(
        "Refresh Interval (seconds)", 5, 60, 10, key="refresh_slider"
    )
    st.caption(f"Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}")

    st.divider()
    st.subheader("ðŸ§ª Development Tools")
    if st.button("ðŸ§¹ Clear All Data", use_container_width=True):
        try:
            if DB_PATH.exists():
                DB_PATH.unlink()
            if LIVE_DATA_JSON.exists():
                LIVE_DATA_JSON.unlink()
            if AI_STATUS_JSON.exists():
                AI_STATUS_JSON.unlink()
            st.success("âœ… All data files cleared!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"Error clearing data: {e}")


# --- Main Page Content ---
st.title("ðŸš€ AI Trading Bot Dashboard")
trades_df = read_trades_from_sqlite()
live_data = load_live_data()
ai_status = load_ai_status()

# --- Status Indicators ---
col_status1, col_status2, col_status3 = st.columns(3)
col_status1.info(f"ðŸ“Š Trades Logged: {len(trades_df)}")
col_status2.info(f"âš¡ Live Data: {'Connected' if live_data else 'Not Found'}")
col_status3.info(f"ðŸ§  AI Status: {'Loaded' if ai_status else 'Not Found'}")

# --- Tabs ---
tab1, tab2, tab3, tab4 = st.tabs(
    [
        "ðŸ“Š Overview & Live Data",
        "ðŸ“ˆ Performance",
        "ðŸ”„ Trade History",
        "âš™ï¸ System Info",
    ]
)

with tab1:
    col_main, col_ai = st.columns([3, 1])
    with col_main:
        st.subheader("ðŸ’° Portfolio Overview")
        exits_df = trades_df[trades_df["action"] == "EXIT"].copy()
        if not exits_df.empty:
            total_pnl = exits_df["pnl_usdt"].sum()
            total_trades = len(exits_df)
            win_rate = (
                (len(exits_df[exits_df["pnl_usdt"] > 0]) / total_trades * 100)
                if total_trades > 0
                else 0
            )
            avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        else:
            total_pnl, total_trades, win_rate, avg_pnl = 0, 0, 0, 0
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total P&L ($)", f"{total_pnl:.2f}")
        m2.metric("Total Trades", total_trades)
        m3.metric("Win Rate (%)", f"{win_rate:.1f}")
        m4.metric("Avg P&L/Trade ($)", f"{avg_pnl:.2f}")
    with col_ai:
        st.subheader("ðŸ§  AI Status")
        if ai_status:
            sentiment = ai_status.get("sentiment", "Unknown")
            if sentiment == "Bullish":
                st.success(f"**{sentiment}**")
            elif sentiment == "Bearish":
                st.error(f"**{sentiment}**")
            else:
                st.warning(f"**{sentiment}**")
        else:
            st.info("Waiting...")
    st.divider()
    st.subheader("âš¡ Live Price Chart")
    if live_data and live_data.get("prices"):
        prices = live_data["prices"]
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(x=list(range(len(prices))), y=prices, mode="lines", name="Price")
        )
        fig.update_layout(template="plotly_dark", height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No live data available.")

with tab2:
    st.subheader("ðŸ“ˆ Performance Analysis")
    if not trades_df.empty:
        exits_df = trades_df[trades_df["action"] == "EXIT"].copy()
        if not exits_df.empty:
            exits_df["cumulative_pnl"] = exits_df["pnl_usdt"].cumsum()
            fig = px.line(
                exits_df,
                x="ts_iso",
                y="cumulative_pnl",
                title="Cumulative P&L Over Time",
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No performance data to display.")

with tab3:
    st.subheader("ðŸ”„ Trade History")
    if not trades_df.empty:
        st.dataframe(
            trades_df.sort_values("ts_iso", ascending=False).head(100),
            use_container_width=True,
        )
    else:
        st.info("No trades recorded yet.")

with tab4:
    st.subheader("âš™ï¸ System Information")
    st.write("**ðŸ“ File Status:**")
    files_status = {
        "Bot Script": BOT_SCRIPT_PATH.exists(),
        "Config File": CONFIG_JSON.exists(),
        "Trades DB": DB_PATH.exists(),
        "Live Data": LIVE_DATA_JSON.exists(),
        "AI Status": AI_STATUS_JSON.exists(),
    }
    for file_name, exists in files_status.items():
        st.write(f"{'âœ…' if exists else 'âš ï¸'} {file_name}")
    st.divider()
    st.write("**âš™ï¸ Current Configuration:**")
    st.json(load_config())
    st.divider()
    st.write("**ðŸ’» Bot Process Info:**")
    if bot_info["running"]:
        st.write(f"- PID: `{bot_info['pid']}`")
        st.write(f"- Status: `{bot_info['status']}`")
        st.write(f"- CPU Usage: `{bot_info['cpu_percent']:.1f}%`")
        st.write(f"- Memory Usage: `{bot_info['memory_mb']:.1f} MB`")
    else:
        st.info("Bot is not currently running.")

# --- Auto-Refresh Logic ---
if auto_refresh:
    time.sleep(refresh_interval)
    st.session_state.last_refresh = datetime.now()
    st.rerun()
