import time
from unittest.mock import MagicMock

import pytest

from config.settings import Settings

# Adjust import path based on your project structure
from trading.risk_manager import RiskManager


# Mock classes to simulate the environment
class MockAIAnalyzer:
    def __init__(self, sentiment="Neutral", last_analysis_time=None):
        self.sentiment = sentiment
        self.last_analysis_time = last_analysis_time or time.time()

    def get_current_sentiment(self):
        return self.sentiment


@pytest.fixture
def mock_env():
    """Pytest fixture to set up a clean testing environment."""
    config = Settings()
    ai_analyzer = MockAIAnalyzer()
    metrics = MagicMock()
    risk_manager = RiskManager(config, ai_analyzer, metrics)
    return risk_manager, metrics, ai_analyzer, config


def test_risk_gate_rejections(mock_env):
    """Verify that each risk gate rejects trades and increments the correct metric."""
    risk_manager, metrics, ai_analyzer, config = mock_env
    signal = {"action": "enter_long"}

    # 1. Test Stale AI Rejection
    ai_analyzer.last_analysis_time = time.time() - (config.ai_max_age_s + 10)
    assert not risk_manager.approve_trade(signal, 1000, {})
    metrics.risk_rejections_total.labels.assert_called_with(reason="stale_ai")

    # 2. Test AI Sentiment Rejection
    ai_analyzer.last_analysis_time = time.time()
    ai_analyzer.sentiment = "Bearish"
    assert not risk_manager.approve_trade(signal, 1000, {})
    metrics.risk_rejections_total.labels.assert_called_with(reason="ai_sentiment")
    ai_analyzer.sentiment = "Bullish"  # Reset for next tests

    # 3. Test Drawdown Rejection
    risk_manager.start_day(1000)
    assert not risk_manager.approve_trade(signal, 970, {})  # > 2% drawdown
    metrics.risk_rejections_total.labels.assert_called_with(reason="drawdown_limit")
