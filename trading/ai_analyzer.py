import os
import time
from openai import OpenAI
import json
from datetime import datetime

class AI_Analyzer:
    def __init__(self):
        try:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.sentiment = "Neutral"
            self.last_analysis_time = 0
            self.cache_duration = 60 * 15 # Cache sentiment for 15 minutes
            print("AI_Analyzer Initialized.")
        except Exception as e:
            print(f"Error initializing OpenAI client: {e}")
            self.client = None

    def get_current_sentiment(self):
        """Returns the cached sentiment."""
        return self.sentiment

    def refresh_sentiment(self):
        """Fetches news, updates sentiment, and saves status to a file."""
        current_time = time.time()
        if (current_time - self.last_analysis_time) < self.cache_duration:
            return

        print("AI sentiment cache expired. Requesting new analysis...")
        headlines = self._fetch_market_news()
        self.sentiment = self._get_sentiment_from_ai(headlines)
        self.last_analysis_time = current_time
        print(f"--- New AI Sentiment: {self.sentiment} ---")

        status = {
            "sentiment": self.sentiment,
            "headlines": headlines,
            "last_updated": datetime.now().isoformat()
        }
        try:
            with open("ai_status.json", "w") as f:
                json.dump(status, f, indent=4)
        except Exception as e:
            print(f"Error saving AI status file: {e}")

    def _fetch_market_news(self):
        """Placeholder for fetching news."""
        return [
            "Bitcoin surges past resistance as institutional interest grows.",
            "Ethereum developers announce successful merge update, network efficiency up.",
            "Regulatory concerns in Asia cast a shadow over short-term crypto market.",
        ]

    def _get_sentiment_from_ai(self, headlines):
        """Analyzes headlines using the OpenAI API."""
        if not self.client: return "Neutral"
        formatted_headlines = "\n- ".join(headlines)
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a financial analyst. Analyze the sentiment of crypto news headlines. Respond with only a single word: Bullish, Bearish, or Neutral."},
                    {"role": "user", "content": f"Headlines:\n- {formatted_headlines}"}
                ],
                temperature=0, max_tokens=5
            )
            sentiment = response.choices[0].message.content.strip()
            return sentiment if sentiment in ["Bullish", "Bearish", "Neutral"] else "Neutral"
        except Exception as e:
            print(f"OpenAI API error: {e}")
            return "Neutral"
