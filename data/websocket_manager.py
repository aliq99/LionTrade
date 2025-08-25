import asyncio
import json
import websockets
import time

class WebSocketManager:
    def __init__(self, url, strategy, risk_manager, execution_engine, ai_analyzer):
        self._url = url
        self.strategy = strategy
        self.risk_manager = risk_manager
        self.execution_engine = execution_engine
        self.ai_analyzer = ai_analyzer
        self.ws = None

    async def connect(self):
        """Establishes a persistent WebSocket connection with a reconnect loop."""
        while True:
            try:
                print("Connecting to WebSocket...")
                async with websockets.connect(self._url) as ws:
                    self.ws = ws
                    print("WebSocket connected.")
                    await self.subscribe()
                    await self.listen()
            except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK) as e:
                print(f"WebSocket connection closed: {e}. Reconnecting in 5 seconds...")
            except Exception as e:
                print(f"An error occurred: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

    async def subscribe(self):
        """Subscribes to the necessary data streams for scalping."""
        symbols = ["BTC_USDT", "ETH_USDT"] 
        ticker_channels = [f"ticker.{symbol}" for symbol in symbols]
        book_channels = [f"book.{symbol}.10" for symbol in symbols]

        subscription_request = {
            "id": int(time.time()),
            "method": "subscribe",
            "params": {"channels": ticker_channels + book_channels},
            "nonce": int(time.time() * 1000)
        }
        await self.ws.send(json.dumps(subscription_request))
        print(f"Subscribed to channels: {ticker_channels + book_channels}")

    async def listen(self):
        """Listens for incoming messages and routes them."""
        self.ai_analyzer.refresh_sentiment()
        
        async for message in self.ws:
            data = json.loads(message)
            
            if data.get("method") == "public/heartbeat":
                await self.ws.send(json.dumps({
                    "id": data.get("id"),
                    "method": "public/respond-heartbeat"
                }))
                continue

            self.ai_analyzer.refresh_sentiment()
            self._route_data(data)

    def _route_data(self, data):
        """Parses data, gets signal, checks risk, and passes to execution."""
        result = data.get('result', {})
        channel = result.get('channel', '')
        
        if not result or 'data' not in result:
            return

        if channel.startswith('ticker.'):
            for tick in result['data']:
                tick_data = {'symbol': tick.get('i'), 'price': tick.get('a'), 'volume': tick.get('v')}
                signal = self.strategy.on_tick_update(tick_data)
                
                if signal:
                    current_budget = self.execution_engine.budget
                    if self.risk_manager.approve_trade(signal, current_budget):
                        self.execution_engine.act(signal)

        elif channel.startswith('book.'):
            order_book_data = result['data'][0] 
            self.strategy.on_order_book_update(order_book_data)
