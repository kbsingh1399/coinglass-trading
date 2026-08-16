import asyncio, websockets
async def test():
    async with websockets.connect('wss://fstream.binance.com/ws/btcusdt@aggTrade') as ws:
        print('Connected')
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print(msg)
asyncio.run(test())
