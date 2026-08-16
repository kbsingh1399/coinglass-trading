import asyncio, websockets
async def test():
    async with websockets.connect('wss://stream.binancefuture.com/ws/btcusdt@aggTrade') as ws:
        print('Connected testnet')
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        print(msg)
asyncio.run(test())
