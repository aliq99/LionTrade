# metrics/telemetry.py
import datetime as dt
import json
import pathlib

from prometheus_client import Counter, Gauge, start_http_server


class _Metrics:
    def __init__(self):
        # bot flow
        self.signals_total = Counter("signals_total", "Signals emitted", ["action"])
        self.trades_entered_total = Counter("trades_entered_total", "Executed entries")
        self.trades_exited_total = Counter("trades_exited_total", "Executed exits")
        self.risk_rejections_total = Counter(
            "risk_rejections_total", "Risk rejections", ["reason"]
        )
        self.reconnects_total = Counter("ws_reconnects_total", "WebSocket reconnects")
        # AI
        self.ai_refresh_total = Counter(
            "ai_refresh_total", "AI refresh attempts", ["result"]
        )
        self.ai_sentiment_value = Gauge("ai_sentiment_value", "AI sentiment as -1,0,1")
        self.ai_confidence = Gauge("ai_confidence", "AI sentiment confidence 0..1")
        # portfolio
        self.budget_usdt = Gauge("budget_usdt", "Current buying power in USDT")
        self.open_positions = Gauge("open_positions", "Open positions count")


METRICS = _Metrics()

_STATUS_PATH = pathlib.Path(__file__).resolve().parents[1] / "budget_status.json"


def write_budget_status(budget: float, open_positions: int = 0):
    """Persist budget/open positions for the UI."""
    try:
        data = {
            "budget_usdt": float(budget),
            "open_positions": int(open_positions),
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        }
        with open(_STATUS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        # best-effort write only
        pass


def start_metrics_server(port: int):
    start_http_server(int(port))
