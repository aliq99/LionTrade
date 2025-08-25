import os
from openai import OpenAI

class AIStrategy:
    def __init__(self, cfg):
        self.cfg = cfg
        try:
            self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            print("AIStrategy Initialized: OpenAI client created successfully.")
        except Exception as e:
            print(f"Error initializing OpenAI client: {e}")
            self.client = None

    def fetch_market_news(self):
        """
        Placeholder for fetching news. In a real bot, this would
        connect to a news API (e.g., NewsAPI.org, CryptoPanic).
        For now, we'll use sample headlines.
        """
        print("Fetching sample market news...")
        sample_headlines = [
            "Bitcoin surges past resistance as institutional interest grows.",
            "Ethereum developers announce successful merge update, network efficiency up.",
            "Regulatory concerns in Asia cast a shadow over short-term crypto market.",
            "Major investment bank launches a dedicated crypto trading desk.",
            "Fear & Greed Index moves into 'Extreme Greed' territory."
        ]
        return sample_headlines

    def get_sentiment_from_ai(self, headlines):
        """
        Analyzes a list of headlines using the OpenAI API and returns
        a sentiment score: 'Bullish', 'Bearish', or 'Neutral'.
        """
        if not self.client:
            print("Cannot get sentiment: OpenAI client not initialized.")
            return "Neutral"

        formatted_headlines = "\n- ".join(headlines)

        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a financial analyst specializing in cryptocurrency markets. Analyze the sentiment of the following news headlines. Respond with only a single word: Bullish, Bearish, or Neutral."
                    },
                    {
                        "role": "user",
                        "content": f"Here are the latest headlines:\n- {formatted_headlines}"
                    }
                ],
                temperature=0,
                max_tokens=5
            )
            
            sentiment = response.choices[0].message.content.strip()
            
            if sentiment in ["Bullish", "Bearish", "Neutral"]:
                return sentiment
            else:
                print(f"Warning: AI returned an unexpected response: '{sentiment}'")
                return "Neutral"

        except Exception as e:
            print(f"An error occurred while calling the OpenAI API: {e}")
            return "Neutral"
    
    def run_analysis_cycle(self):
        """
        Runs a full cycle of fetching news and getting sentiment.
        """
        headlines = self.fetch_market_news()
        sentiment = self.get_sentiment_from_ai(headlines)
        print(f"Overall market sentiment: {sentiment}")
        return sentiment
