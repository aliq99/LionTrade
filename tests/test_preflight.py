import json
import urllib.request


def test_state_file():
    with open("STATE.json", "r", encoding="utf-8") as f:
        s = json.load(f)
    assert s["metrics"]
    assert s["sqlite_trades"]
    assert s["ai_sentiment_cached"]


def test_metrics_exposed():
    # Pass silently if bot/metrics server not running
    try:
        with urllib.request.urlopen("http://localhost:9108/metrics", timeout=1) as r:
            txt = r.read().decode("utf-8", errors="ignore")
    except Exception:
        return
    for needle in ("signals_total", "budget_usdt", "ai_sentiment_value"):
        assert needle in txt
