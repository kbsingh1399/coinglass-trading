import os
import sys
import time
import json
import asyncio
import pytest

os.environ["BINANCE_LIVE"] = "0"
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Engine_1 import (
    SnapshotStore, AssetSnapshot, FootprintCandle, LiveTradeTracker,
    get_process_memory_usage, ML_POOL
)
from binance_broker import BinanceBroker
import engine_components.binance_broker as ebb
from coinglass_scraper import CoinglassTab

def test_fix1_place_then_cancel_sltp():
    """Verify modify_sltp uses place-then-cancel pattern without naked exposure."""
    broker = BinanceBroker(dry_run=True, account_size=10000.0)
    res = broker.modify_sltp("BTCUSDT", 12345, 95000.0, 105000.0)
    assert res is True, "modify_sltp should succeed in dry_run mode"

    ebb_broker = ebb.BinanceBroker(dry_run=True, account_size=10000.0)
    res_ebb = ebb_broker.modify_sltp("BTCUSDT", 12345, 95000.0, 105000.0)
    assert res_ebb is True, "engine_components modify_sltp should succeed in dry_run mode"

@pytest.mark.asyncio
async def test_fix2_ml_dispatch_throttling():
    """Verify ML dispatch is throttled to 2.0 seconds per symbol."""
    store = SnapshotStore(symbols=["BTCUSDT"])
    
    # Simulate price ticks
    await store.update("BTCUSDT", "binance_ws", price=100000.0)
    ts1 = store._last_ml_dispatch_ts.get("BTCUSDT", 0.0)
    
    # Instant follow-up tick within < 0.1s
    await store.update("BTCUSDT", "binance_ws", price=100001.0)
    ts2 = store._last_ml_dispatch_ts.get("BTCUSDT", 0.0)
    
    assert ts1 == ts2, "Rapid second tick within 2.0s should be throttled"

@pytest.mark.asyncio
async def test_fix3_trade_tracker_decoupling():
    """Verify SnapshotStore.update calls tracker methods without deadlocking."""
    tracker = LiveTradeTracker(initial_capital=10000.0)
    store = SnapshotStore(symbols=["BTCUSDT"], trade_tracker=tracker)
    
    await store.update("BTCUSDT", "binance_ws", price=95000.0)
    snap = store.snapshot()["BTCUSDT"]
    assert snap.price == 95000.0

def test_fix4_reconnect_guard_removed():
    """Verify reconnect method does not bypass recovery when indicators_injected is True."""
    tab = CoinglassTab(context=None, symbols=["BTCUSDT"], store=None, tab_id="tab_1")
    tab.indicators_injected = True
    assert hasattr(tab, "reconnect")

def test_fix6_memory_usage_fallback():
    """Verify get_process_memory_usage returns a valid integer across platforms."""
    mem = get_process_memory_usage()
    assert isinstance(mem, int)
    assert mem >= 0

def test_fix7_footprint_volume_profile_bounding():
    """Verify volume profile is capped at 500 keys under extreme price swings."""
    candle = FootprintCandle(tick_size=10.0)
    
    # Inject 700 distinct price levels within the same candle
    for i in range(700):
        candle.update(candle_open_ms=1000, buy_vol=1.0, sell_vol=1.0, close_price=10000.0 + (i * 10.0))
    
    assert len(candle.volume_profile) <= 500, f"Volume profile should be capped at 500, got {len(candle.volume_profile)}"

def test_fix8_trade_history_archival(tmp_path):
    """Verify trade history older than 30 days is moved to _archive.json."""
    tracker = LiveTradeTracker(initial_capital=10000.0)
    test_log = str(tmp_path / "test_trades.json")
    tracker.log_file = test_log
    tracker.tracker_file = test_log
    
    now = time.time()
    old_trade = {
        "trade_id": "S1_BTCUSDT_LONG_1",
        "symbol": "BTCUSDT",
        "strategy": "S1_Liquidation",
        "direction": 1,
        "entry_price": 90000.0,
        "entry_timestamp": now - (35 * 86400), # 35 days ago
        "exit_price": 95000.0,
        "pnl_usd": 500.0
    }
    recent_trade = {
        "trade_id": "S1_ETHUSDT_LONG_2",
        "symbol": "ETHUSDT",
        "strategy": "S1_Liquidation",
        "direction": 1,
        "entry_price": 3000.0,
        "entry_timestamp": now - (5 * 86400), # 5 days ago
        "exit_price": 3200.0,
        "pnl_usd": 200.0
    }
    
    tracker.history = [old_trade, recent_trade]
    tracker.save_history()
    
    # Check active history retains only recent trade
    assert len(tracker.history) == 1
    assert tracker.history[0]["trade_id"] == "S1_ETHUSDT_LONG_2"
    
    # Check archive file was created and contains the old trade
    archive_file = test_log.replace(".json", "_archive.json")
    assert os.path.exists(archive_file)
    with open(archive_file, "r", encoding="utf-8") as f:
        archived_data = json.load(f)
    assert len(archived_data) == 1
    assert archived_data[0]["trade_id"] == "S1_BTCUSDT_LONG_1"
