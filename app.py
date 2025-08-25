import streamlit as st
import pandas as pd
import json
import time
import plotly.graph_objects as go
import plotly.express as px
import pathlib
from datetime import datetime, timedelta
import subprocess
import os
import sys

# --- Initialize Session State for the bot process ---
if 'bot_process' not in st.session_state:
    st.session_state.bot_process = None
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# --- Page and File Setup ---
st.set_page_config(
    page_title="AI Trading Bot Dashboard", 
    layout="wide", 
    initial_sidebar_state="expanded",
    page_icon="🤖"
)

# --- Define Full Paths for Subprocess ---
BASE_DIR = pathlib.Path(__file__).parent

# Better cross-platform Python executable detection
if os.name == 'nt':  # Windows
    PYTHON_EXECUTABLE = BASE_DIR / "venv" / "Scripts" / "python.exe"
    if not PYTHON_EXECUTABLE.exists():
        PYTHON_EXECUTABLE = "python"  # Fallback to system Python
else:  # Linux/Mac
    PYTHON_EXECUTABLE = BASE_DIR / "venv" / "bin" / "python"
    if not PYTHON_EXECUTABLE.exists():
        PYTHON_EXECUTABLE = sys.executable  # Use current Python

BOT_SCRIPT_PATH = BASE_DIR / "crypto_com_momo_bot.py"

# File paths
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
        
        # Handle column name variations
        df = df.rename(columns={
            "ts": "ts_iso", 
            "timestamp": "ts_iso", 
            "pnl": "pnl_usdt", 
            "amount": "qty"
        })
        
        # Ensure all required columns exist
        for c in cols:
            if c not in df.columns: 
                df[c] = pd.NA
        
        # Convert data types
        for c in ["price", "qty", "pnl_usdt"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        
        df["ts_iso"] = pd.to_datetime(df["ts_iso"], errors="coerce")
        df = df.sort_values("ts_iso", ascending=True).reset_index(drop=True)
        
        return df[cols]
    
    except Exception as e:
        st.error(f"Error reading trades file: {e}")
        return pd.DataFrame(columns=cols)

def load_live_data():
    """Load live market data with error handling - NO CACHING."""
    try:
        if LIVE_DATA_JSON.exists():
            # Force read the file every time
            with open(LIVE_DATA_JSON, "r") as f:
                data = json.load(f)
            
            # Debug: Show what data structure we're getting
            if st.sidebar.checkbox("Debug Live Data", key="debug_live"):
                st.sidebar.write("Live data structure:")
                st.sidebar.json(data)
                st.sidebar.write(f"File size: {LIVE_DATA_JSON.stat().st_size} bytes")
                st.sidebar.write(f"Last modified: {datetime.fromtimestamp(LIVE_DATA_JSON.stat().st_mtime)}")
            
            return data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        st.warning(f"Could not load live data: {e}")
    except Exception as e:
        st.error(f"Unexpected error loading live data: {e}")
    
    return None

def load_ai_status():
    """Load AI sentiment/status data."""
    if AI_STATUS_JSON.exists():
        try:
            with open(AI_STATUS_JSON, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    return None

def load_config():
    """Load bot configuration."""
    try:
        if CONFIG_JSON.exists():
            with open(CONFIG_JSON, "r") as f:
                return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return {}

def save_config(config):
    """Save bot configuration."""
    try:
        with open(CONFIG_JSON, "w") as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        st.error(f"Error saving config: {e}")
        return False

def is_bot_running():
    """Check if bot process is still running."""
    if st.session_state.bot_process is None:
        return False
    
    try:
        # Check if process is still alive
        poll = st.session_state.bot_process.poll()
        if poll is None:
            return True  # Still running
        else:
            st.session_state.bot_process = None
            return False  # Process ended
    except:
        st.session_state.bot_process = None
        return False

def start_bot():
    """Start the trading bot subprocess."""
    if is_bot_running():
        return False, "Bot is already running"
    
    if not BOT_SCRIPT_PATH.exists():
        return False, f"Bot script not found: {BOT_SCRIPT_PATH}"
    
    try:
        # Start the bot process
        st.session_state.bot_process = subprocess.Popen(
            [str(PYTHON_EXECUTABLE), str(BOT_SCRIPT_PATH)],
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return True, f"Bot started successfully! (PID: {st.session_state.bot_process.pid})"
    
    except Exception as e:
        return False, f"Failed to start bot: {e}"

def stop_bot():
    """Stop the trading bot subprocess."""
    if not is_bot_running():
        return False, "Bot is not running"
    
    try:
        st.session_state.bot_process.terminate()
        st.session_state.bot_process.wait(timeout=10)  # Wait up to 10 seconds
        st.session_state.bot_process = None
        return True, "Bot stopped successfully"
    
    except subprocess.TimeoutExpired:
        # Force kill if it doesn't terminate gracefully
        st.session_state.bot_process.kill()
        st.session_state.bot_process = None
        return True, "Bot force-stopped"
    
    except Exception as e:
        return False, f"Error stopping bot: {e}"

# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Bot Controls")
    
    existing_config = load_config()
    
    # Strategy Selection
    strategy_options = ["Momentum", "Scalping"]
    default_strategy_name = existing_config.get("strategy_name", "scalping").title()
    strategy_choice = st.selectbox(
        "Choose Strategy", 
        strategy_options, 
        index=strategy_options.index(default_strategy_name) if default_strategy_name in strategy_options else 1
    )

    # Basic Settings
    symbol = st.text_input(
        "Symbol", 
        value=existing_config.get("symbol_ccxt", "BTC/USDT")
    )
    
    total_budget = st.number_input(
        "Total Budget (USDT)", 
        min_value=1.0, 
        value=float(existing_config.get("total_budget_usdt", 1000.0)), 
        step=100.0
    )

    # Strategy-specific settings
    if strategy_choice == "Momentum":
        st.subheader("Momentum Settings")
        ema_len = st.slider(
            "EMA Length", 
            10, 200, 
            int(existing_config.get("ema_len", 12)), 
            key="momentum_ema"
        )
        zscore_entry = st.slider(
            "Z-Score Entry", 
            0.1, 3.0, 
            float(existing_config.get("zscore_entry", 0.4)), 
            0.1, 
            key="momentum_zscore"
        )
    
    elif strategy_choice == "Scalping":
        st.subheader("Scalping Settings")
        risk_per_trade_pct = st.slider(
            "Risk Per Trade (%)", 
            0.1, 25.0, 
            float(existing_config.get("risk_per_trade_pct", 0.01)) * 100, 
            0.1, 
            key="scalping_risk"
        )
        sl_pct = st.slider(
            "Stop Loss (%)", 
            0.1, 5.0, 
            float(existing_config.get("stop_loss_pct", 0.005)) * 100, 
            0.1, 
            key="scalping_sl"
        )
        tp_pct = st.slider(
            "Take Profit (%)", 
            0.1, 5.0, 
            float(existing_config.get("take_profit_pct", 0.005)) * 100, 
            0.1, 
            key="scalping_tp"
        )
        rsi_oversold = st.slider(
            "RSI Oversold Level", 
            5, 45, 
            int(existing_config.get("rsi_oversold", 30)), 
            key="scalping_rsi_os"
        )
        rsi_overbought = st.slider(
            "RSI Overbought Level", 
            55, 95, 
            int(existing_config.get("rsi_overbought", 70)), 
            key="scalping_rsi_ob"
        )

    # Save Settings
    if st.button("💾 Save Settings", type="primary", use_container_width=True):
        new_config = {
            "strategy_name": strategy_choice.lower(),
            "symbol_ccxt": symbol,
            "total_budget_usdt": total_budget,
            "last_updated": datetime.now().isoformat()
        }
        
        if strategy_choice == "Momentum":
            new_config.update({
                "ema_len": ema_len,
                "zscore_entry": zscore_entry
            })
        elif strategy_choice == "Scalping":
            new_config.update({
                "risk_per_trade_pct": risk_per_trade_pct / 100,
                "stop_loss_pct": sl_pct / 100,
                "take_profit_pct": tp_pct / 100,
                "rsi_oversold": rsi_oversold,
                "rsi_overbought": rsi_overbought
            })
        
        if save_config(new_config):
            st.success(f"✅ {strategy_choice} settings saved!")
        else:
            st.error("❌ Failed to save settings!")

    st.divider()

    # Bot Control Buttons
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("▶️ Start Bot", use_container_width=True):
            success, message = start_bot()
            if success:
                st.success(message)
                time.sleep(1)
                st.rerun()
            else:
                st.error(message)
    
    with col2:
        if st.button("⏹️ Stop Bot", use_container_width=True):
            success, message = stop_bot()
            if success:
                st.success(message)
                time.sleep(1)
                st.rerun()
            else:
                st.warning(message)

    st.divider()
    
    # Bot Status Display
    st.subheader("🤖 Bot Status")
    if is_bot_running():
        st.success(f"✅ Running (PID: {st.session_state.bot_process.pid})")
    else:
        st.info("⚪ Stopped")
    
    # Auto-refresh controls
    st.subheader("🔄 Auto-Refresh")
    auto_refresh = st.checkbox("Enable Auto-Refresh", value=True)
    refresh_interval = st.slider("Refresh Interval (seconds)", 5, 60, 10, key="refresh_slider")
    
    # Show last refresh time
    st.caption(f"Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}")
    
    st.divider()
    
    # Test Data Generator
    st.subheader("🧪 Test Live Data")
    st.caption("Generate fake price data to test the chart")
    
    if st.button("📊 Generate Test Data", use_container_width=True):
        import random
        
        # Generate realistic price movement
        base_price = 45000.0  # Starting BTC price
        num_points = 20
        prices = []
        timestamps = []
        
        current_time = datetime.now()
        
        for i in range(num_points):
            # Random walk with some trend
            if i == 0:
                price = base_price
            else:
                # Small random changes (-1% to +1%)
                change_pct = random.uniform(-0.01, 0.01)
                price = prices[-1] * (1 + change_pct)
            
            prices.append(round(price, 2))
            timestamp = (current_time - timedelta(minutes=num_points-i)).isoformat()
            timestamps.append(timestamp)
        
        test_data = {
            "prices": prices,
            "timestamps": timestamps,
            "last_update": datetime.now().isoformat(),
            "symbol": symbol,
            "test_data": True,
            "current_price": prices[-1],
            "price_change": prices[-1] - prices[0] if len(prices) > 1 else 0
        }
        
        try:
            # Ensure directory exists
            LIVE_DATA_JSON.parent.mkdir(parents=True, exist_ok=True)
            
            with open(LIVE_DATA_JSON, "w") as f:
                json.dump(test_data, f, indent=2)
            
            st.success("✅ Test data generated!")
            st.write(f"📊 Generated {len(prices)} price points")
            st.write(f"💰 Price range: ${min(prices):.2f} - ${max(prices):.2f}")
            
            time.sleep(2)
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Failed to generate test data: {e}")
            st.write(f"Attempted to write to: {LIVE_DATA_JSON}")
            
    # Add a button to generate CHANGING test data
    if st.button("🔄 Generate Changing Test Data", use_container_width=True):
        import random
        
        # Load existing test data or create new
        existing_data = None
        if LIVE_DATA_JSON.exists():
            try:
                with open(LIVE_DATA_JSON, "r") as f:
                    existing_data = json.load(f)
            except:
                pass
        
        if existing_data and existing_data.get("test_data"):
            # Modify existing data
            prices = existing_data.get("prices", [45000.0])
            timestamps = existing_data.get("timestamps", [])
            
            # Add new price point
            last_price = prices[-1] if prices else 45000.0
            change_pct = random.uniform(-0.02, 0.02)  # -2% to +2%
            new_price = last_price * (1 + change_pct)
            
            prices.append(round(new_price, 2))
            timestamps.append(datetime.now().isoformat())
            
            # Keep only last 50 points
            if len(prices) > 50:
                prices = prices[-50:]
                timestamps = timestamps[-50:]
        else:
            # Create new data
            prices = [45000.0 + random.uniform(-100, 100)]
            timestamps = [datetime.now().isoformat()]
        
        test_data = {
            "prices": prices,
            "timestamps": timestamps,
            "last_update": datetime.now().isoformat(),
            "symbol": symbol,
            "test_data": True,
            "current_price": prices[-1],
            "price_change": prices[-1] - prices[0] if len(prices) > 1 else 0
        }
        
        try:
            with open(LIVE_DATA_JSON, "w") as f:
                json.dump(test_data, f, indent=2)
            
            st.success(f"✅ Updated test data! Price: ${prices[-1]:.2f}")
            time.sleep(1)
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Failed to update test data: {e}")
    
    if st.button("🗑️ Clear Test Data", use_container_width=True):
        try:
            if LIVE_DATA_JSON.exists():
                os.remove(LIVE_DATA_JSON)
            st.success("✅ Test data cleared!")
            time.sleep(1)
            st.rerun()
        except Exception as e:
            st.error(f"❌ Failed to clear test data: {e}")

# --- Main Dashboard Content ---
st.title("🚀 AI Trading Bot Dashboard")

# Force reload data every time - no caching
if st.button("🔄 Force Refresh Data", key="force_refresh"):
    st.rerun()

# Load data fresh every time
trades_df = read_trades_df()
live_data = load_live_data()
ai_status = load_ai_status()

# Show data loading status
col_status1, col_status2, col_status3 = st.columns(3)
with col_status1:
    if not trades_df.empty:
        st.success(f"✅ Trades: {len(trades_df)} rows")
    else:
        st.info("📊 No trades data")

with col_status2:
    if live_data:
        st.success("✅ Live data loaded")
    else:
        st.warning("⚠️ No live data")

with col_status3:
    if ai_status:
        st.success("✅ AI status loaded")  
    else:
        st.info("🤖 No AI status")

# Create tabs
tab1, tab2, tab3, tab4 = st.tabs(["📊 Overview & Live Data", "📈 Performance", "🔄 Trade History", "⚙️ System Info"])

with tab1:
    # Two-column layout for main content and AI status
    col_main, col_ai = st.columns([3, 1])
    
    with col_main:
        st.subheader("💰 Portfolio Overview")
        
        # Calculate metrics from EXIT trades only
        exits_df = trades_df[trades_df['action'] == 'EXIT'].copy()
        
        if not exits_df.empty:
            total_pnl = exits_df["pnl_usdt"].sum()
            total_trades = len(exits_df)
            winning_trades = len(exits_df[exits_df["pnl_usdt"] > 0])
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
            
            # Calculate daily P&L
            exits_df['date'] = exits_df['ts_iso'].dt.date
            today_pnl = exits_df[exits_df['date'] == datetime.now().date()]['pnl_usdt'].sum()
        else:
            total_pnl, total_trades, win_rate, avg_pnl, today_pnl = 0, 0, 0, 0, 0
        
        # Display metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total P&L", f"${total_pnl:.2f}", delta=f"+${today_pnl:.2f} today" if today_pnl != 0 else None)
        m2.metric("Total Trades", total_trades)
        m3.metric("Win Rate", f"{win_rate:.1f}%")
        m4.metric("Avg P&L/Trade", f"${avg_pnl:.2f}")

    with col_ai:
        st.subheader("🧠 AI Status")
        if ai_status:
            sentiment = ai_status.get("sentiment", "Unknown")
            confidence = ai_status.get("confidence", 0)
            last_update = ai_status.get("timestamp", "Unknown")
            
            # Display sentiment with appropriate colors
            if sentiment == "Bullish":
                st.success(f"**{sentiment}** 📈")
            elif sentiment == "Bearish":
                st.error(f"**{sentiment}** 📉")
            else:
                st.warning(f"**{sentiment}** ➡️")
            
            # Show additional AI info
            if confidence > 0:
                st.caption(f"Confidence: {confidence:.1%}")
            st.caption(f"Updated: {last_update}")
        else:
            st.info("⏳ Waiting for AI analysis...")
    
    st.divider()
    
    # Live Price Chart
    st.subheader("⚡ Live Price Chart")
    
    # Debug information
    col_debug1, col_debug2, col_debug3 = st.columns(3)
    with col_debug1:
        if LIVE_DATA_JSON.exists():
            file_mod_time = datetime.fromtimestamp(LIVE_DATA_JSON.stat().st_mtime)
            time_diff = (datetime.now() - file_mod_time).total_seconds()
            st.caption(f"📁 File modified: {file_mod_time.strftime('%H:%M:%S')}")
            if time_diff > 60:
                st.caption(f"⚠️ File is {time_diff:.0f}s old!")
            else:
                st.caption(f"✅ File is {time_diff:.0f}s old")
        else:
            st.caption("📁 live_data.json not found")
    
    with col_debug2:
        st.caption(f"🔄 Current time: {datetime.now().strftime('%H:%M:%S')}")
        st.caption(f"🔄 Refresh count: {st.session_state.get('refresh_count', 0)}")
    
    with col_debug3:
        if live_data:
            st.caption(f"📊 Data keys: {list(live_data.keys())}")
            if live_data.get("test_data"):
                st.caption("🧪 Using test data")
            else:
                st.caption("📈 Using live bot data")
    
    if live_data:
        st.write("**Live Data Keys Available:**", list(live_data.keys()))
        
        # Try different possible data structures
        prices = None
        timestamps = None
        
        # Check for different possible data structures
        if "prices" in live_data:
            prices = live_data["prices"]
            timestamps = live_data.get("timestamps", list(range(len(prices))))
        elif "price_history" in live_data:
            prices = live_data["price_history"]
            timestamps = live_data.get("time_history", list(range(len(prices))))
        elif "data" in live_data and isinstance(live_data["data"], list):
            prices = live_data["data"]
            timestamps = list(range(len(prices)))
        elif "price" in live_data:
            # Single price point - create a simple list
            current_price = live_data["price"]
            prices = [current_price]
            timestamps = [datetime.now().strftime("%H:%M:%S")]
            st.info("📊 Showing single price point. Bot may need time to collect historical data.")
        
        if prices and len(prices) > 0:
            # Handle different timestamp formats
            if timestamps and len(timestamps) > 0:
                # Try to parse timestamps if they're strings
                if isinstance(timestamps[0], str):
                    try:
                        parsed_timestamps = [pd.to_datetime(ts) for ts in timestamps]
                        timestamps = parsed_timestamps
                    except:
                        # If parsing fails, use indices
                        timestamps = list(range(len(prices)))
            else:
                timestamps = list(range(len(prices)))
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=timestamps, 
                y=prices, 
                mode='lines+markers',
                name='Price',
                line=dict(color='#00d4ff', width=2),
                marker=dict(size=4 if len(prices) < 50 else 2)
            ))
            
            fig.update_layout(
                template="plotly_dark",
                height=350,
                title=f"{symbol} Live Price ({len(prices)} data points)",
                xaxis_title="Time",
                yaxis_title="Price (USDT)",
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Show current price and change
            if len(prices) >= 2:
                current_price = prices[-1]
                price_change = prices[-1] - prices[-2]
                price_change_pct = (price_change / prices[-2]) * 100 if prices[-2] != 0 else 0
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Current Price", f"${current_price:.4f}")
                col2.metric("Price Change", f"${price_change:.4f}", f"{price_change_pct:.2f}%")
                col3.metric("Data Points", len(prices))
            elif len(prices) == 1:
                col1, col2 = st.columns(2)
                col1.metric("Current Price", f"${prices[0]:.4f}")
                col2.metric("Data Points", len(prices))
        else:
            st.warning("📊 No price data found in live_data.json")
            st.write("**Expected data structures:**")
            st.code("""
{
  "prices": [1234.56, 1235.67, 1236.78, ...],
  "timestamps": ["2024-01-01 10:00:00", "2024-01-01 10:01:00", ...]
}
OR
{
  "price": 1234.56,
  "timestamp": "2024-01-01 10:00:00"
}
            """)
    else:
        st.warning("📊 No live price data available.")
        st.write("**Troubleshooting steps:**")
        st.write("1. ✅ Make sure the bot is running")
        st.write("2. 📝 Check if `live_data.json` is being created")
        st.write("3. 🔄 Verify the bot is updating the file regularly")
        st.write("4. 🐛 Enable 'Debug Live Data' in sidebar to see data structure")

with tab2:
    st.subheader("📈 Performance Analysis")
    
    if not trades_df.empty:
        exits_df = trades_df[trades_df['action'] == 'EXIT'].copy()
        
        if not exits_df.empty:
            # Cumulative P&L chart
            exits_df["cumulative_pnl"] = exits_df["pnl_usdt"].cumsum()
            
            fig = px.line(
                exits_df, 
                x="ts_iso", 
                y="cumulative_pnl",
                title="Cumulative P&L Over Time",
                labels={"cumulative_pnl": "Cumulative P&L (USDT)", "ts_iso": "Time"}
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
            
            # Additional performance metrics
            col1, col2 = st.columns(2)
            
            with col1:
                # P&L distribution histogram
                fig_hist = px.histogram(
                    exits_df,
                    x="pnl_usdt",
                    title="P&L Distribution",
                    nbins=20,
                    labels={"pnl_usdt": "P&L (USDT)"}
                )
                st.plotly_chart(fig_hist, use_container_width=True)
            
            with col2:
                # Daily trading activity
                exits_df["date"] = exits_df["ts_iso"].dt.date
                daily_stats = exits_df.groupby("date").agg({
                    "pnl_usdt": ["count", "sum"]
                }).reset_index()
                daily_stats.columns = ["date", "trades", "pnl"]
                
                fig_daily = px.bar(
                    daily_stats,
                    x="date",
                    y="trades",
                    title="Daily Trading Activity",
                    labels={"trades": "Number of Trades"}
                )
                st.plotly_chart(fig_daily, use_container_width=True)
        else:
            st.info("No completed trades to analyze yet.")
    else:
        st.info("📊 No performance data to display. Start trading to see analytics here.")

with tab3:
    st.subheader("🔄 Trade History")
    
    if not trades_df.empty:
        # Trade history with better formatting
        display_df = trades_df.sort_values("ts_iso", ascending=False).head(100)
        
        st.dataframe(
            display_df,
            use_container_width=True,
            column_config={
                "ts_iso": st.column_config.DatetimeColumn("Timestamp", format="MMM DD, HH:mm:ss"),
                "pnl_usdt": st.column_config.NumberColumn("P&L (USDT)", format="%.2f"),
                "price": st.column_config.NumberColumn("Price", format="%.4f"),
                "qty": st.column_config.NumberColumn("Quantity", format="%.6f"),
                "action": st.column_config.TextColumn("Action"),
                "side": st.column_config.TextColumn("Side"),
                "reason": st.column_config.TextColumn("Reason")
            },
            height=400
        )
        
        # Trade summary
        st.subheader("📋 Trade Summary")
        entries = len(trades_df[trades_df['action'] == 'ENTRY'])
        exits = len(trades_df[trades_df['action'] == 'EXIT'])
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Entries", entries)
        col2.metric("Total Exits", exits)
        col3.metric("Open Positions", entries - exits)
        
    else:
        st.info("📝 No trade history available yet.")

with tab4:
    st.subheader("⚙️ System Information")
    
    # File status
    st.write("**📁 File Status:**")
    files_status = {
        "Bot Script": BOT_SCRIPT_PATH.exists(),
        "Config File": CONFIG_JSON.exists(),
        "Trades CSV": TRADES_CSV.exists(),
        "Live Data": LIVE_DATA_JSON.exists(),
        "AI Status": AI_STATUS_JSON.exists()
    }
    
    for file_name, exists in files_status.items():
        if exists:
            st.success(f"✅ {file_name}")
        else:
            st.warning(f"⚠️ {file_name} - Not Found")
    
    # Current configuration
    st.write("**⚙️ Current Configuration:**")
    if existing_config:
        st.json(existing_config)
    else:
        st.info("No configuration saved yet.")
    
    # Live data file contents
    st.write("**📊 Live Data File Contents:**")
    if LIVE_DATA_JSON.exists():
        try:
            with open(LIVE_DATA_JSON, "r") as f:
                live_file_contents = f.read()
            st.code(live_file_contents, language="json")
            
            file_size = LIVE_DATA_JSON.stat().st_size
            st.caption(f"File size: {file_size} bytes")
        except Exception as e:
            st.error(f"Error reading live data file: {e}")
    else:
        st.warning("live_data.json file does not exist")
    
    # System info
    st.write("**💻 System Info:**")
    st.write(f"- Python Executable: `{PYTHON_EXECUTABLE}`")
    st.write(f"- Working Directory: `{BASE_DIR}`")
    st.write(f"- Bot Process Status: {'Running' if is_bot_running() else 'Stopped'}")
    
    # Bot process info
    if is_bot_running():
        st.write(f"- Bot PID: {st.session_state.bot_process.pid}")
        try:
            poll_result = st.session_state.bot_process.poll()
            st.write(f"- Process Poll: {poll_result}")
        except:
            st.write("- Process Poll: Unable to check")

# --- Auto-Refresh Logic ---
if auto_refresh:
    # Increment refresh counter
    if 'refresh_count' not in st.session_state:
        st.session_state.refresh_count = 0
    st.session_state.refresh_count += 1
    
    time.sleep(refresh_interval)
    st.session_state.last_refresh = datetime.now()
    st.rerun()
