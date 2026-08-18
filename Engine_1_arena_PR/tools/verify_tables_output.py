import os
import sys
import asyncio
import time

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from six_strategy_engine import LiveSixStrategyPredictor
from Engine_1 import ALL_SYMBOLS, SnapshotStore, render_table
from rich.console import Console

async def main():
    print("[Test] Initializing LiveSixStrategyPredictor with ALL_SYMBOLS...")
    predictor = LiveSixStrategyPredictor(ALL_SYMBOLS)
    predictor.load_history_from_disk(max_candles=250)
    
    store = SnapshotStore(ALL_SYMBOLS, predictor=predictor)
    
    # Simulate a tick/snapshot update for each symbol
    for sym in ALL_SYMBOLS:
        hist = predictor.candles_history.get(sym, [])
        if hist:
            latest = hist[-1]
            price = float(latest.get("close", latest.get("Close", 100.0)))
            await store.update(
                sym,
                source="test",
                price=price,
                volume=float(latest.get("volume", latest.get("Volume", 1000.0))),
                rsi=float(latest.get("rsi", 52.4)),
                fut_cvd=float(latest.get("fut_cvd", latest.get("CVD", 15000.0))),
                spot_cvd=float(latest.get("spot_cvd", latest.get("Spot_CVD", 5000.0))),
                funding=float(latest.get("funding", latest.get("Funding", 0.0001))),
                oi=float(latest.get("oi", latest.get("OI", 2500000.0))),
                coins_bid=5000.0,
                coins_ask=-4000.0,
                dollars_bid=price * 5000.0,
                dollars_ask=-price * 4000.0,
            )

    snap = store.snapshot()
    history_map = predictor.candles_history
    layout = render_table(snap, trade_tracker=None, store=store)
    
    console = Console(width=160, color_system="truecolor", record=True)
    console.print(layout)

if __name__ == "__main__":
    asyncio.run(main())
