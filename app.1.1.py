import streamlit as st
import pandas as pd
import json
import time
import plotly.graph_objects as go
import plotly.express as px
import pathlib
from datetime import datetime
import subprocess
import os

# --- Initialize Session State for the bot process ---
if 'bot_process' not in st.session_state:
    st.session_state.bot_process = None

# --- Page and File Setup ---
st.set_page_config(page_title="AI Trading Bot Dashboard", layout="wide", initial_sidebar_state="expanded")

# --- Define Full Paths for Subprocess ---
# This ensures the script can find the bot and python executable
BASE_DIR = pathlib.Path(__file__).parent
PYTHON_EXECUTABLE = BASE_DIR / "venv" / "Scripts" / "python.exe"
BOT_SCRIPT_PATH = BASE_DIR / "crypto_com_momo_bot.py"

TRADES_CSV = BASE_DIR / "trades.csv"
CONFIG_JSON = BASE_DIR / "config.json"
LIVE_DATA_JSON = BASE_DIR / "live_data.json"
AI_STATUS_JSON = BASE_DIR / "ai_status.json"

# --- Helper Functions ---
def read_trades_df():
    """Reads and cleans the historical trades.csv file."""
    cols = ["ts_iso", "symbol", "action", "side", "price", "qty", "reason", "pnl_usdt"]
    if not TRADES_CSV.exists() or TRADES_CSV.stat().st_size == 0:
        return pd.DataFrame(columns=cols)
    try:
        df = pd.read_csv(TRADES_CSV, engine="python", on_bad_lines="skip")
        df = df.rename(columns={"ts": "ts_iso", "timestamp": "ts_iso", "pnl": "pnl_usdt", "amount": "qty"})
        for c in cols:
            if c not in df.columns: df[c] = pd.NA
        for c in ["price", "qty", "pnl_usdt"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["ts_iso"] = pd.to_datetime(df["ts_iso"], errors="coerce")
        df = df.sort_values("ts_iso", ascending=True).reset_index(drop=True)
        return df[cols]
    except Exception as e:
        st.error(f"Error reading trades file: {e}")
        return pd.DataFrame(columns=cols)

def load_live_data():
    if LIVE_DATA_JSON.exists():
        try:
            with open(LIVE_DATA_JSON, "r") as f: return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): pass
    return None

def load_ai_status():
    if AI_STATUS_JSON.exists():
        try:
            with open(AI_STATUS_JSON, "r") as f: return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError): pass
    return None

def load_config():
    if CONFIG_JSON.exists():
        with open(CONFIG_JSON, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    with open(CONFIG_JSON, "w") as f:
        json.dump(config, f, indent=4)

# --- Sidebar ---
with st.sidebar:
    st.header("⚙️ Bot Controls")
    existing_config = load_config()
    
    strategy_options = ["Momentum", "Scalping"]
    default_strategy_name = existing_config.get("strategy_name", "scalping").title()
    strategy_choice = st.selectbox("Choose Strategy", strategy_options, index=strategy_options.index(default_strategy_name) if default_strategy_name in strategy_options else 0)

    symbol = st.text_input("Symbol", value=existing_config.get("symbol_ccxt", "BTC/USDT"))
    total_budget = st.number_input("Total Budget (USDT)", min_value=1.0, value=float(existing_config.get("total_budget_usdt", 1000.0)), step=100.0)

    if strategy_choice == "Scalping":
        st.subheader("Scalping Settings")
        risk_per_trade_pct = st.slider("Risk Per Trade (%)", 0.1, 25.0, float(existing_config.get("risk_per_trade_pct", 1.0)) * 100, 0.1, key="scalping_risk")
        sl_pct = st.slider("Stop Loss (%)", 0.1, 5.0, float(existing_config.get("stop_loss_pct", 0.5)) * 100, 0.1, key="scalping_sl")
        tp_pct = st.slider("Take Profit (%)", 0.1, 5.0, float(existing_config.get("take_profit_pct", 0.5)) * 100, 0.1, key="scalping_tp")
        rsi_oversold = st.slider("RSI Oversold Level", 5, 45, int(existing_config.get("rsi_oversold", 30)), key="scalping_rsi_os")
        rsi_overbought = st.slider("RSI Overbought Level", 55, 95, int(existing_config.get("rsi_overbought", 70)), key="scalping_rsi_ob")

    if st.button("💾 Save Settings", type="primary", use_container_width=True):
        new_config = {"strategy_name": strategy_choice.lower(), "symbol_ccxt": symbol, "total_budget_usdt": total_budget, "last_updated": datetime.now().isoformat()}
        if strategy_choice == "Scalping":
            new_config.update({"risk_per_trade_pct": risk_per_trade_pct / 100, "stop_loss_pct": sl_pct / 100, "take_profit_pct": tp_pct / 100, "rsi_oversold": rsi_oversold, "rsi_overbought": rsi_overbought})
        save_config(new_config)
        st.sidebar.success(f"✅ {strategy_choice} settings saved!")

    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Start Bot", use_container_width=True):
            if st.session_state.bot_process is None:
                st.session_state.bot_process = subprocess.Popen([str(PYTHON_EXECUTABLE), str(BOT_SCRIPT_PATH)])
                st.success(f"Bot started! (PID: {st.session_state.bot_process.pid})")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("Bot is already running.")
    
    with col2:
        if st.button("⏹️ Stop Bot", use_container_width=True):
            if st.session_state.bot_process is not None:
                st.session_state.bot_process.terminate()
                st.session_state.bot_process = None
                st.success("Bot stopped!")
                time.sleep(1)
                st.rerun()
            else:
                st.warning("Bot is not running.")

    st.divider()
    st.subheader("Bot Status")
    if st.session_state.bot_process and st.session_state.bot_process.poll() is None:
        st.success(f"✅ Running (PID: {st.session_state.bot_process.pid})")
    else:
        st.info("⚪ Stopped")
        st.session_state.bot_process = None
    
    auto_refresh = st.checkbox("Enable Auto-Refresh", value=True)
    refresh_interval = st.slider("Refresh Interval (seconds)", 5, 60, 10, key="refresh_slider")
    
# --- Main Page Content ---
st.title("🚀 AI Trading Bot Dashboard")

trades_df = read_trades_df()
live_data = load_live_data()
ai_status = load_ai_status()

tab1, tab2, tab3 = st.tabs(["📊 Overview & Live Data", "📈 Performance", "🔄 Trade History"])

with tab1:
    col_main, col_ai = st.columns([3, 1])
    with col_main:
        st.subheader("Portfolio Overview")
        exits_df = trades_df[trades_df['action'] == 'EXIT'].copy()
        if not exits_df.empty:
            total_pnl = exits_df["pnl_usdt"].sum()
            total_trades = len(exits_df)
            win_rate = (len(exits_df[exits_df["pnl_usdt"] > 0]) / total_trades * 100)
            avg_pnl = total_pnl / total_trades
        else:
            total_pnl, total_trades, win_rate, avg_pnl = 0, 0, 0, 0
            
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total P&L ($)", f"{total_pnl:.2f}")
        m2.metric("Total Trades", total_trades)
        m3.metric("Win Rate (%)", f"{win_rate:.1f}")
        m4.metric("Avg P&L/Trade ($)", f"{avg_pnl:.2f}")

    with col_ai:
        st.subheader("🧠 AI Status")
        if ai_status:
            sentiment = ai_status.get("sentiment", "Unknown")
            if sentiment == "Bullish": st.success(f"**{sentiment}**")
            elif sentiment == "Bearish": st.error(f"**{sentiment}** (Longs Blocked)")
            else: st.warning(f"**{sentiment}**")
        else:
            st.info("Waiting...")
    
    st.divider()
    st.subheader("⚡ Live Price Chart")
    if live_data and live_data.get("prices"):
        prices = live_data["prices"]
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=list(range(len(prices))), y=prices, mode='lines', name='Price', line=dict(color='cyan')))
        fig.update_layout(template="plotly_dark", height=350)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No live data available. Make sure the bot is running.")

with tab2:
    st.subheader("Performance Analysis")
    if not trades_df.empty:
        exits_df = trades_df[trades_df['action'] == 'EXIT'].copy()
        if not exits_df.empty:
            exits_df["cumulative_pnl"] = exits_df["pnl_usdt"].cumsum()
            fig = px.line(exits_df, x="ts_iso", y="cumulative_pnl", title="Cumulative P&L Over Time")
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No performance data to display.")

with tab3:
    st.subheader("Trade History")
    st.dataframe(trades_df.sort_values("ts_iso", ascending=False).head(100), use_container_width=True)

# --- Auto-Refresh Logic ---
if auto_refresh:
    time.sleep(refresh_interval)
    st.rerun()
