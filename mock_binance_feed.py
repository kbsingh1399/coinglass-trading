#!/usr/bin/env python3
"""
Mock Binance WebSocket + REST Feed Server
==========================================
Emits synthetic tick streams on ws://localhost:8765 and serves
mock kline data on http://localhost:8766 to bypass the sandbox
network restrictions.

Usage:
    python mock_binance_feed.py
"""

import asyncio
import json
import time
import math
import random
import websockets
from aiohttp import web

# ─── Synthetic Market Data ───────────────────────────────────────────
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT",
    "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT",
    "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT"
]

BASE_PRICES = {
    "BTCUSDT": 64000.0, "ETHUSDT": 3400.0, "XRPUSDT": 0.55,
    "SOLUSDT": 150.0, "BNBUSDT": 580.0, "DOGEUSDT": 0.12,
    "ADAUSDT": 0.35, "TRXUSDT": 0.13, "LINKUSDT": 14.5,
    "AVAXUSDT": 25.0, "SUIUSDT": 3.5, "NEARUSDT": 5.2,
    "DOTUSDT": 6.8, "LTCUSDT": 65.0
}

# Volatility per symbol (percentage per tick)
VOLATILITY = {
    "BTCUSDT": 0.0003, "ETHUSDT": 0.0004, "XRPUSDT": 0.0008,
    "SOLUSDT": 0.0006, "BNBUSDT": 0.0004, "DOGEUSDT": 0.001,
    "ADAUSDT": 0.0007, "TRXUSDT": 0.0005, "LINKUSDT": 0.0006,
    "AVAXUSDT": 0.0007, "SUIUSDT": 0.0009, "NEARUSDT": 0.0008,
    "DOTUSDT": 0.0007, "LTCUSDT": 0.0005
}

# Current prices (will drift)
current_prices = dict(BASE_PRICES)
# Track 15m candle data
candle_data = {}
for sym in SYMBOLS:
    candle_data[sym] = {
        "open": BASE_PRICES[sym],
        "high": BASE_PRICES[sym],
        "low": BASE_PRICES[sym],
        "close": BASE_PRICES[sym],
        "volume": random.uniform(1000, 50000),
        "buy_volume": random.uniform(500, 25000),
    }


def generate_tick(sym: str) -> dict:
    """Generate a realistic synthetic aggTrade tick."""
    vol = VOLATILITY.get(sym, 0.0005)
    price = current_prices[sym]
    
    # Random walk with mean reversion
    drift = (BASE_PRICES[sym] - price) * 0.001  # mean reversion
    shock = random.gauss(0, vol) * price
    price = max(price * 0.5, price + drift + shock)  # floor at 50% of base
    current_prices[sym] = price
    
    # Update candle
    cd = candle_data[sym]
    cd["close"] = price
    cd["high"] = max(cd["high"], price)
    cd["low"] = min(cd["low"], price) if cd["low"] > 0 else price
    cd["volume"] += random.uniform(0.1, 5.0)
    cd["buy_volume"] += random.uniform(0.05, 2.5)
    
    # Check if new 15m candle
    now_ms = int(time.time() * 1000)
    candle_open_ms = (now_ms // 900000) * 900000
    if candle_open_ms != cd.get("candle_open_ms", 0):
        cd["candle_open_ms"] = candle_open_ms
        cd["open"] = price
        cd["high"] = price
        cd["low"] = price
        cd["volume"] = random.uniform(100, 5000)
        cd["buy_volume"] = random.uniform(50, 2500)
    
    is_buyer_maker = random.random() < 0.48
    
    return {
        "stream": f"{sym.lower()}@aggTrade",
        "data": {
            "e": "aggTrade",
            "E": now_ms,
            "s": sym.upper(),
            "a": random.randint(100000, 999999),
            "p": f"{price:.8f}",
            "q": f"{random.uniform(0.001, 2.0):.4f}",
            "f": random.randint(100000, 999999),
            "l": random.randint(100000, 999999),
            "T": now_ms,
            "m": is_buyer_maker,
        }
    }


# ─── WebSocket Server ────────────────────────────────────────────────
async def ws_handler(websocket):
    """Handle WebSocket connections and stream synthetic ticks."""
    print(f"[Mock WS] Client connected from {websocket.remote_address}")
    try:
        while True:
            for sym in SYMBOLS:
                tick = generate_tick(sym)
                await websocket.send(json.dumps(tick))
                await asyncio.sleep(0.002)  # ~500 ticks/sec across all symbols
    except websockets.exceptions.ConnectionClosed:
        print(f"[Mock WS] Client disconnected")
    except Exception as e:
        print(f"[Mock WS] Error: {e}")


# ─── REST API Server (Mock Binance Futures Klines) ───────────────────
async def handle_klines(request):
    """Mock /fapi/v1/klines endpoint."""
    sym = request.query.get("symbol", "BTCUSDT")
    cd = candle_data.get(sym)
    if not cd:
        return web.json_response([])
    
    now_ms = int(time.time() * 1000)
    candle_open_ms = (now_ms // 900000) * 900000
    
    # Generate synthetic kline data
    kline = [
        candle_open_ms,                    # Open time
        f"{cd['open']:.8f}",               # Open
        f"{cd['high']:.8f}",               # High
        f"{cd['low']:.8f}",                # Low
        f"{cd['close']:.8f}",              # Close
        f"{cd['volume']:.4f}",             # Volume
        candle_open_ms + 899999,           # Close time
        f"{cd['volume'] * cd['close']:.4f}",  # Quote asset volume
        random.randint(100, 5000),         # Number of trades
        f"{cd['buy_volume']:.4f}",         # Taker buy base asset volume
        f"{cd['buy_volume'] * cd['close']:.4f}",  # Taker buy quote asset volume
        "0"                                # Ignore
    ]
    return web.json_response([kline])


async def handle_ping(request):
    """Mock /fapi/v1/ping endpoint."""
    return web.json_response({})


# ─── Main ────────────────────────────────────────────────────────────
async def main():
    # Start REST API server
    app = web.Application()
    app.router.add_get("/fapi/v1/klines", handle_klines)
    app.router.add_get("/fapi/v1/ping", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8766)
    await site.start()
    print(f"[Mock REST] Running on http://localhost:8766")
    
    # Start WebSocket server
    print(f"[Mock WS] Starting on ws://0.0.0.0:8765")
    async with websockets.serve(ws_handler, "0.0.0.0", 8765):
        print(f"[Mock WS] Running on ws://localhost:8765")
        print(f"[Mock WS] Streaming {len(SYMBOLS)} symbols with synthetic ticks")
        print(f"[Mock REST] Serving klines for {len(SYMBOLS)} symbols")
        print(f"")
        print(f"Set these environment variables to use the mock feeds:")
        print(f"  export BINANCE_WS_URL=ws://localhost:8765")
        print(f"  export BINANCE_REST_URL=http://localhost:8766")
        print(f"")
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
