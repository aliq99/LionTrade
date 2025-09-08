from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Defines all settings for the application.
    Reads from a .env file and environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Execution Settings ---
    execution_mode: str = "auto"
    large_order_threshold_usdt: float = 500.0
    twap_duration_minutes: int = 30
    twap_order_slices: int = 10

    # --- Risk Management Settings ---
    max_spread_pct: float = 0.001
    daily_drawdown_pct: float = 0.02
    ai_max_age_s: int = 900
    min_top_depth: float = 0.0
    throttle_window: int = 20
    throttle_threshold_pct: float = 0.40

    # --- Budget & Position Settings ---
    total_budget_usdt: float = 1000.0
    risk_per_trade_pct: float = 0.01
    stop_loss_pct: float = 0.004
    take_profit_pct: float = 0.01

    # --- Strategy-Specific Settings ---
    ema_fast_len: int = 9
    ema_slow_len: int = 21
    rsi_len: int = 14
    rsi_oversold: float = 30
    rsi_overbought: float = 70
    zscore_entry: float = 0.4  # For Momentum

    # --- General Settings ---
    strategy_name: str = "scalping"
    symbol_ccxt: str = "BTC/USDT"
    ws_url: str = "wss://stream.crypto.com/exchange/v1/market"
    paper: bool = True
    metrics_port: int = 9108
    log_level: str = "INFO"
    cooldown_sec: int = 10


def load_settings() -> Settings:
    """Loads and returns the application settings."""
    return Settings()


# Create a single, importable instance of the settings
cfg: Settings = load_settings()
bot_config = cfg.model_dump()
