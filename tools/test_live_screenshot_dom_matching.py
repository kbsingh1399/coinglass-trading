import asyncio
import io
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from rich.console import Console
from Engine_1 import SnapshotStore, render_table, AssetSnapshot

async def test_live_screenshot_matching():
    symbols = ["BTCUSDT", "ETHUSDT", "XRPUSDT"]
    store = SnapshotStore(symbols)
    
    # 1. Update BTCUSDT with exact screenshot values
    await store.update(
        "BTCUSDT",
        source="coinglass",
        price=63464.60,
        volume=39_155_000.0,
        rsi=47.59,
        fut_cvd=3356.0,
        spot_cvd=1676.0,
        funding=0.006181,
        liq_long=6111.0,
        liq_short=0.0,
        ls_ratio=1.8540,
        oi=347_136.0,
        whale=-41.3050,
        tk_buy=3912.0,
        tk_sell=-5097.0,
        coins_bid=7113.0,
        dollars_bid=449_525_000.0,
        atr_14=94.6,
        atr_100=75.0,
        ema_8=63938.3,
        ema_21=64207.2,
        ema_50=64391.0,
        ema_200=64391.4,
        ema_800=63668.9
    )
    
    # 2. Update ETHUSDT with exact screenshot values
    await store.update(
        "ETHUSDT",
        source="coinglass",
        price=1897.02,
        volume=27_202_000.0,
        rsi=45.11,
        fut_cvd=5203.0,
        spot_cvd=-552.3654,
        funding=0.006428,
        liq_long=4177.0,
        liq_short=-491.43,
        ls_ratio=2.4040,
        oi=7_240_000.0,
        whale=-82.0400,
        tk_buy=5118.0,
        tk_sell=6076.0,
        coins_bid=157_000.0,
        dollars_bid=296_854_000.0,
        atr_14=3.61,
        atr_100=3.12,
        ema_8=1899.24,
        ema_21=1899.90,
        ema_50=1896.72,
        ema_200=1888.22,
        ema_800=1891.70
    )

    # 3. Update XRPUSDT with exact screenshot values
    await store.update(
        "XRPUSDT",
        source="coinglass",
        price=0.9980,
        volume=1_015_000.0,
        rsi=45.59,
        fut_cvd=-59_955_000.0,
        spot_cvd=-17_146_000.0,
        funding=0.004827,
        liq_long=488.31,
        liq_short=0.0,
        ls_ratio=3.1570,
        oi=1_354_000_000.0,
        whale=-159.8300,
        tk_buy=1651.0,
        tk_sell=-1543.0,
        coins_bid=42_654_000.0,
        dollars_bid=42_426_000.0,
        atr_14=0.0018,
        atr_100=0.0018,
        ema_8=0.9987,
        ema_21=0.9994,
        ema_50=0.9996,
        ema_200=1.0005,
        ema_800=1.0121
    )

    snaps = store.snapshot()
    
    # Assertions for BTC
    btc = snaps["BTCUSDT"]
    assert btc.liq_long == 6111.0, f"Expected Liq L 6111.0, got {btc.liq_long}"
    assert btc.dollars_bid == 449_525_000.0, f"Expected Dollars Bid 449.525M, got {btc.dollars_bid}"
    assert btc.coins_bid == 7113.0, f"Expected Coins Bid 7113.0, got {btc.coins_bid}"
    print(f"[PASS] BTCUSDT: Liq L={btc.liq_long:,.0f} | Bid ($)=${btc.dollars_bid/1e6:.1f}M | Bid (C)={btc.coins_bid:,.0f} BTC")

    # Assertions for ETH
    eth = snaps["ETHUSDT"]
    assert eth.liq_long == 4177.0, f"Expected Liq L 4177.0, got {eth.liq_long}"
    assert eth.liq_short == -491.43, f"Expected Liq S -491.43, got {eth.liq_short}"
    assert eth.dollars_bid == 296_854_000.0, f"Expected Dollars Bid 296.854M, got {eth.dollars_bid}"
    assert eth.coins_bid == 157_000.0, f"Expected Coins Bid 157K, got {eth.coins_bid}"
    print(f"[PASS] ETHUSDT: Liq L={eth.liq_long:,.0f} | Liq S={eth.liq_short:,.2f} | Bid ($)=${eth.dollars_bid/1e6:.1f}M | Bid (C)={eth.coins_bid/1e3:.1f}K ETH")

    # Assertions for XRP
    xrp = snaps["XRPUSDT"]
    assert xrp.liq_long == 488.31, f"Expected Liq L 488.31, got {xrp.liq_long}"
    assert xrp.dollars_bid == 42_426_000.0, f"Expected Dollars Bid 42.4M, got {xrp.dollars_bid}"
    assert xrp.coins_bid == 42_654_000.0, f"Expected Coins Bid 42.6M, got {xrp.coins_bid}"
    print(f"[PASS] XRPUSDT: Liq L={xrp.liq_long:,.2f} | Bid ($)=${xrp.dollars_bid/1e6:.1f}M | Bid (C)={xrp.coins_bid/1e6:.1f}M XRP")

    # Render terminal table and write to live_data/live_terminal_table.txt
    string_buf = io.StringIO()
    console = Console(file=string_buf, force_terminal=False, color_system=None, width=220)
    tbl = render_table(snaps, store.trade_tracker, store)
    console.print(tbl)
    output = string_buf.getvalue()
    
    with open("live_data/live_terminal_table.txt", "w", encoding="utf-8") as f:
        f.write(output)
    
    print("\n--- Rendered Terminal Table Output ---")
    for line in output.splitlines()[:20]:
        print(line)

if __name__ == "__main__":
    asyncio.run(test_live_screenshot_matching())
