import asyncio
import json
import logging
import os
import random
import time

import pandas as pd  # for pd.Timestamp.utcnow()
import websockets


class WebSocketManager:
    def __init__(self, url, strategy, risk_manager, execution_engine, ai_analyzer):
        self._url = url
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.execution_engine = execution_engine
        self.ai_analyzer = ai_analyzer

        self.ws = None
        self.log = logging.getLogger("momo")
        self._reconnect_attempts = 0  # for backoff

        # latest top-of-book snapshot for risk gating
        self._best_bid = None
        self._best_ask = None
        self._best_bid_size = None
        self._best_ask_size = None

    def _backoff(self, attempt: int, base: float = 0.5, cap: float = 30.0) -> float:
        """Exponential backoff + jitter."""
        return min(cap, base * (2**attempt)) + random.uniform(0, base)

    async def connect(self):
        """Persistent connection with exponential backoff + jitter."""
        while True:
            try:
                self.log.info("Connecting to WebSocket...")
                async with websockets.connect(self._url) as ws:
                    self.ws = ws
                    self._reconnect_attempts = 0  # reset on success
                    self.log.info("WebSocket connected.")
                    await self.subscribe()
                    await self.listen()
            except (
                websockets.ConnectionClosedError,
                websockets.ConnectionClosedOK,
            ) as e:
                delay = self._backoff(self._reconnect_attempts)
                self._reconnect_attempts += 1
                self.log.info(
                    "WebSocket closed: %s. Reconnecting in %.1fs...", e, delay
                )
                await asyncio.sleep(delay)
            except Exception as e:
                delay = self._backoff(self._reconnect_attempts)
                self._reconnect_attempts += 1
                self.log.info("WebSocket error: %s. Reconnecting in %.1fs...", e, delay)
                await asyncio.sleep(delay)

    async def subscribe(self):
        """Subscribe to ticker and level-10 order book for symbols."""
        symbols = ["BTC_USDT", "ETH_USDT"]
        ticker_channels = [f"ticker.{symbol}" for symbol in symbols]
        book_channels = [f"book.{symbol}.10" for symbol in symbols]

        subscription_request = {
            "id": int(time.time()),
            "method": "subscribe",
            "params": {"channels": ticker_channels + book_channels},
            "nonce": int(time.time() * 1000),
        }
        await self.ws.send(json.dumps(subscription_request))
        self.log.info("Subscribed to: %s", ticker_channels + book_channels)

    async def listen(self):
        """Route inbound messages. No AI calls here."""
        async for message in self.ws:
            data = json.loads(message)

            # Heartbeat handling
            if data.get("method") == "public/heartbeat":
                try:
                    await self.ws.send(
                        json.dumps(
                            {"id": data.get("id"), "method": "public/respond-heartbeat"}
                        )
                    )
                except Exception:
                    pass
                continue

            self._route_data(data)

    def _route_data(self, data):
        """Parses data, adds a timestamp, and calls the appropriate strategy method."""
        result = data.get("result", {})
        channel = result.get("channel", "")

        if not result or "data" not in result:
            return

        # Get the current time once for all ticks in this message
        now_ts = pd.Timestamp.utcnow()

        if channel.startswith("ticker."):
            for tick in result["data"]:
                tick_data = {
                    "symbol": tick.get("i"),
                    "price": tick.get("a"),
                    "volume": tick.get("v"),
                    "timestamp": now_ts,  # Inject live timestamp
                }

                # DEBUG: tick + FORCE hook visibility
                try:
                    self.log.debug(
                        "ws tick price=%s force=%s",
                        tick_data["price"],
                        os.getenv("FORCE_SIGNAL"),
                    )
                except Exception:
                    pass

                # Generate a strategy signal
                signal = (
                    self.strategy.on_tick_update(tick_data)
                    if hasattr(self.strategy, "on_tick_update")
                    else None
                )

                # Risk-check and execute
                if signal:
                    current_budget = self.execution_engine.budget
                    book = {
                        "bid": getattr(self.strategy, "latest_bid", self._best_bid),
                        "ask": getattr(self.strategy, "latest_ask", self._best_ask),
                        "bid_size": self._best_bid_size,
                        "ask_size": self._best_ask_size,
                    }
                    now_ts = time.time()
                    if self.risk_manager.approve_trade(
                        signal, current_budget, book=book, now_ts=now_ts
                    ):
                        self.execution_engine.act(signal)

        # -------- ORDER BOOK --------
        elif channel.startswith("book."):
            # crypto.com book payload example:
            # {'bids': [[price, qty], ...], 'asks': [[price, qty], ...], ...}
            ob = result["data"][0] if result["data"] else {}
            try:
                bids = ob.get("bids") or ob.get("b") or []
                asks = ob.get("asks") or ob.get("a") or []
                self._best_bid = float(bids[0][0]) if bids else None
                self._best_ask = float(asks[0][0]) if asks else None
                self._best_bid_size = (
                    float(bids[0][1]) if bids and len(bids[0]) > 1 else None
                )
                self._best_ask_size = (
                    float(asks[0][1]) if asks and len(asks[0]) > 1 else None
                )
            except Exception:
                self._best_bid, self._best_ask = None, None
                self._best_bid_size, self._best_ask_size = None, None

            # Mirror into strategy for execution helpers
            try:
                if hasattr(self.strategy, "latest_bid"):
                    self.strategy.latest_bid = self._best_bid
                if hasattr(self.strategy, "latest_ask"):
                    self.strategy.latest_ask = self._best_ask
            except Exception:
                pass
