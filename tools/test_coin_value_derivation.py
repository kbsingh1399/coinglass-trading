import asyncio
import io
import sys
import os
import dataclasses
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rich.console import Console
from Engine_1 import SnapshotStore, AssetSnapshot, ALL_SYMBOLS, render_table

async def test_bid_ask_resolution():
    print("=== Testing Bid ($) / Ask ($) vs Bid (C) / Ask (C) Resolution ===")
    store = SnapshotStore(ALL_SYMBOLS)
    
    # Test 1: BTCUSDT with Dollar Depth Scraped ($439.2M Bid, -$567.5M Ask, Price=$63,514.80)
    await store.update("BTCUSDT", source="coinglass", price=63514.80, dollars_bid=439_200_000.0, dollars_ask=-567_500_000.0)
    snap_btc = store.snapshot()["BTCUSDT"]
    
    assert snap_btc.dollars_bid == 439_200_000.0, f"Expected 439.2M, got {snap_btc.dollars_bid}"
    assert snap_btc.dollars_ask == -567_500_000.0, f"Expected -567.5M, got {snap_btc.dollars_ask}"
    expected_btc_coins_bid = 439_200_000.0 / 63514.80
    expected_btc_coins_ask = -567_500_000.0 / 63514.80
    assert abs(snap_btc.coins_bid - expected_btc_coins_bid) < 1.0, f"Expected {expected_btc_coins_bid}, got {snap_btc.coins_bid}"
    assert abs(snap_btc.coins_ask - expected_btc_coins_ask) < 1.0, f"Expected {expected_btc_coins_ask}, got {snap_btc.coins_ask}"
    print(f"[PASS] BTCUSDT: Bid ($)=${snap_btc.dollars_bid/1e6:.1f}M -> Bid (C)={snap_btc.coins_bid:,.1f} BTC ({snap_btc.coins_bid/1e3:.1f}K)")
    print(f"[PASS] BTCUSDT: Ask ($)=${snap_btc.dollars_ask/1e6:.1f}M -> Ask (C)={snap_btc.coins_ask:,.1f} BTC ({snap_btc.coins_ask/1e3:.1f}K)")

    # Test 2: ETHUSDT with Dollar Depth ($290.3M Bid, -$296.7M Ask, Price=$1,898.92)
    await store.update("ETHUSDT", source="coinglass", price=1898.92, dollars_bid=290_300_000.0, dollars_ask=-296_700_000.0)
    snap_eth = store.snapshot()["ETHUSDT"]
    expected_eth_coins_bid = 290_300_000.0 / 1898.92
    assert abs(snap_eth.coins_bid - expected_eth_coins_bid) < 1.0
    print(f"[PASS] ETHUSDT: Bid ($)=${snap_eth.dollars_bid/1e6:.1f}M -> Bid (C)={snap_eth.coins_bid:,.1f} ETH ({snap_eth.coins_bid/1e3:.1f}K)")

    # Test 3: Duplication Anomaly Recovery (Scraper accidentally sends 439.2M for both coins_bid and dollars_bid on BTC)
    await store.update("BTCUSDT", source="coinglass", price=63514.80, coins_bid=439_200_000.0, dollars_bid=439_200_000.0, coins_ask=-567_500_000.0, dollars_ask=-567_500_000.0)
    snap_btc_rec = store.snapshot()["BTCUSDT"]
    assert abs(snap_btc_rec.coins_bid - expected_btc_coins_bid) < 1.0, f"Expected recovery to {expected_btc_coins_bid}, got {snap_btc_rec.coins_bid}"
    print(f"[PASS] Duplication Anomaly Recovery: coins_bid automatically resolved to {snap_btc_rec.coins_bid:,.1f} BTC")

    # Test 4: DOGEUSDT ($25.6M Bid, -$24.0M Ask, Price=$0.0700)
    await store.update("DOGEUSDT", source="coinglass", price=0.0700, dollars_bid=25_600_000.0, dollars_ask=-24_000_000.0)
    snap_doge = store.snapshot()["DOGEUSDT"]
    expected_doge_coins_bid = 25_600_000.0 / 0.0700
    assert abs(snap_doge.coins_bid - expected_doge_coins_bid) < 100.0
    print(f"[PASS] DOGEUSDT: Bid ($)=${snap_doge.dollars_bid/1e6:.1f}M -> Bid (C)={snap_doge.coins_bid/1e6:.1f}M DOGE")

    # Test 5: Render terminal table and check plain text string output
    string_buf = io.StringIO()
    console = Console(file=string_buf, force_terminal=False, color_system=None, width=220)
    snaps = store.snapshot()
    tbl = render_table(snaps, store.trade_tracker, store)
    console.print(tbl)
    output = string_buf.getvalue()
    print("\n--- Rendered Terminal Table Preview ---")
    for line in output.splitlines()[:25]:
        print(line)

if __name__ == "__main__":
    asyncio.run(test_bid_ask_resolution())
