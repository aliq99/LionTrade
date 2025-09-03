import datetime as dt
import json
import logging
import os
import pathlib
import time
from typing import Any, Dict, List

from openai import OpenAI

from metrics.telemetry import METRICS

log = logging.getLogger("momo")


def _normalize_label(label: str) -> str:
    if not label:
        return "Neutral"
    line = label.strip().lower()
    mapping = {
        "bull": "Bullish",
        "bullish": "Bullish",
        "based": "Bullish",
        "risk-on": "Bullish",
        "bear": "Bearish",
        "bearish": "Bearish",
        "risk-off": "Bearish",
        "neutral": "Neutral",
        "range": "Neutral",
        "sideways": "Neutral",
        "flat": "Neutral",
        "chop": "Neutral",
    }
    return mapping.get(line, "Neutral")


class AI_Analyzer:
    """Caches sentiment. Writes ai_status.json for UI and updates Prometheus."""

    def __init__(self):
        self.client = OpenAI()
        self.last_label: str = "Neutral"
        self.last_score: float = 0.50
        self.last_analysis_time: float = 0.0
        self.cache_duration: int = int(os.getenv("AI_CACHE_SECONDS", "900"))
        self._status_path = (
            pathlib.Path(__file__).resolve().parents[1] / "ai_status.json"
        )

    def get_current_sentiment(self) -> str:
        return self.last_label

    def _classify(self, headlines: List[str]) -> Dict[str, Any]:
        prompt = (
            "Decide crypto market sentiment from headlines. "
            "Output a single line: <Label> <Score>. Label in {Bullish,Bearish,Neutral}. "
            "Score in [0,1].\n" + "\n".join(f"- {h}" for h in headlines[:10])
        )
        r = self.client.responses.create(
            model=os.getenv("OPENAI_SENTIMENT_MODEL", "gpt-4o-mini"),
            input=prompt,
            temperature=0,
            timeout=8.0,
        )
        text = r.output_text.strip().replace("%", "")
        parts = text.split()
        label = _normalize_label(parts[0] if parts else "")
        try:
            score = float(parts[-1])
            if score > 1:
                score = score / 100.0
        except Exception:
            score = 0.50
        return {"label": label, "score": max(0.0, min(1.0, score))}

    def _write_status(self) -> None:
        try:
            status = {
                "sentiment": self.last_label,
                "confidence": float(self.last_score),
                "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(
                    timespec="seconds"
                ),
            }
            with open(self._status_path, "w", encoding="utf-8") as f:
                json.dump(status, f)
        except Exception:
            pass

    def refresh_sentiment(self, headlines: List[str] = None) -> None:
        if headlines is None:
            headlines = ["Bitcoin steady", "Ethereum mixed"]
        backoffs = [0.2, 0.5, 1.0]
        for i, s in enumerate(backoffs + [None]):
            try:
                res = self._classify(headlines)
                self.last_label = res["label"]
                self.last_score = res["score"]
                self.last_analysis_time = time.time()
                self._write_status()
                # metrics
                METRICS.ai_refresh_total.labels(result="ok").inc()
                METRICS.ai_confidence.set(self.last_score)
                METRICS.ai_sentiment_value.set(
                    1
                    if self.last_label == "Bullish"
                    else (-1 if self.last_label == "Bearish" else 0)
                )
                log.info("AI sentiment: %s (%.2f)", self.last_label, self.last_score)
                return
            except Exception as e:
                if i == len(backoffs):
                    METRICS.ai_refresh_total.labels(result="error").inc()
                    log.error("AI refresh failed: %s", e)
                    return
                time.sleep(s)
