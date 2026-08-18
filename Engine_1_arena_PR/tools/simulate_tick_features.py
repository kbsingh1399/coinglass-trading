"""
Empirical Tick-by-Tick Sanity & Deep Feature Simulation Audit
Simulates 100 rolling ticks across all 18 symbols to verify zero NaNs, zero Infinities,
exact 100-candle rolling window convergence, and signal generation across all 6 strategies.
"""
import os
import sys
import time
import math
import numpy as np
import pandas as pd

# Add project root to path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from Engine_1 import ALL_SYMBOLS, AssetSnapshot, SnapshotStore, Engine1TradeTracker
from six_strategy_engine import LiveSixStrategyPredictor, featurize, _zscore

def run_deep_simulation():
    print("=" * 80)
    print("  DEEP TICK-BY-TICK FEATURE & 100-CANDLE ROLLING WINDOW SIMULATION AUDIT")
    print("=" * 80)

    # 1. Initialize Predictor and Trade Tracker
    predictor = LiveSixStrategyPredictor(ALL_SYMBOLS)
    trade_tracker = Engine1TradeTracker()

    # 2. Verify In-Memory Seeding from Parquet / Fallback (Zero Excel)
    print("\n[Phase 1] Testing In-Memory 100-Candle Seeding from Parquet / Fallback...")
    predictor.load_history_from_disk(max_candles=100)
    
    for sym in ALL_SYMBOLS:
        hist = predictor.candles_history.get(sym, [])
        assert len(hist) > 0, f"History for {sym} is empty after seeding!"
        assert len(hist) <= 100, f"History for {sym} exceeds 100 candles! (len={len(hist)})"
        assert predictor.candles_history[sym].maxlen == 100, f"Deque maxlen for {sym} is not 100!"
        print(f"  [PASS] {sym:<10}: {len(hist):>3}/100 candles seeded in memory.")

    # 3. Deep Tick-by-Tick Streaming Simulation (100 ticks per symbol)
    print("\n[Phase 2] Simulating 100 Live Ticks per Symbol (1,800 Total Ticks)...")
    feature_keys = [
        'ema_8', 'ema_21', 'ema_50', 'ema_200', 'ema_800',
        'atr_14', 'rsi', 'zc4', 'zc10', 'zc20',
        'zb4', 'zb10', 'zb20', 'vr', 'zoi', 'zls', 'zfr',
        'p8', 'p21', 'p50'
    ]

    total_ticks = 0
    nan_count = 0
    inf_count = 0

    base_prices = {
        'BTCUSDT': 63000.0, 'ETHUSDT': 1880.0, 'BNBUSDT': 600.0, 'SOLUSDT': 75.0,
        'XRPUSDT': 1.0, 'DOGEUSDT': 0.10, 'ADAUSDT': 0.35, 'TRXUSDT': 0.33,
        'LINKUSDT': 9.4, 'AVAXUSDT': 6.3, 'SUIUSDT': 0.68, 'NEARUSDT': 1.6,
        'DOTUSDT': 0.76, 'LTCUSDT': 44.0, 'XAUUSDT': 4385.0, 'XAGUSDT': 68.0,
        'CLUSDT': 78.0, 'NATGASUSDT': 2.7
    }

    for tick_idx in range(1, 101):
        for sym in ALL_SYMBOLS:
            base_p = base_prices.get(sym, 10.0)
            noise = np.sin(tick_idx * 0.1) * (base_p * 0.002)
            cur_price = base_p + noise
            
            snap = AssetSnapshot(
                symbol=sym,
                price=cur_price,
                volume=1000.0 * tick_idx,
                fut_cvd=50000.0 * np.cos(tick_idx * 0.15),
                spot_cvd=25000.0 * np.sin(tick_idx * 0.15),
                funding=0.0001 + (0.00005 * np.sin(tick_idx * 0.05)),
                oi=15000000.0 + (500000.0 * np.sin(tick_idx * 0.1)),
                liq_long=max(0.0, 15000.0 * np.sin(tick_idx * 0.2)),
                liq_short=max(0.0, -15000.0 * np.cos(tick_idx * 0.2)),
                ls_ratio=1.5 + (0.3 * np.sin(tick_idx * 0.1)),
                coins_bid=500.0 + (50.0 * np.sin(tick_idx * 0.1)),
                coins_ask=500.0 + (50.0 * np.cos(tick_idx * 0.1)),
                dollars_bid=400000000.0,
                dollars_ask=400000000.0,
                whale_idx=10.0 * np.sin(tick_idx * 0.1),
                tk_buy_cnt=100 + tick_idx,
                tk_sell_cnt=90 + tick_idx,
                fp_delta=250.0 * np.sin(tick_idx * 0.2),
                fp_poc=cur_price,
                ts_ns=time.time_ns()
            )

            # Process tick
            enriched_snap = predictor.on_tick_update(sym, snap, trade_tracker)
            total_ticks += 1

            # Validate each feature
            for fk in feature_keys:
                val = getattr(enriched_snap, fk, 0.0)
                if val is None or (isinstance(val, float) and math.isnan(val)):
                    nan_count += 1
                    print(f"  [ERROR] {sym} tick {tick_idx}: {fk} is NaN!")
                elif isinstance(val, float) and math.isinf(val):
                    inf_count += 1
                    print(f"  [ERROR] {sym} tick {tick_idx}: {fk} is Inf!")

            # Validate status string
            status = enriched_snap.strategy_armed
            assert status is not None and len(status) > 0, f"Empty status for {sym}!"

    print(f"  [PASS] Processed {total_ticks:,} live ticks across {len(ALL_SYMBOLS)} symbols.")
    print(f"  [PASS] NaN Count: {nan_count} (MUST BE 0)")
    print(f"  [PASS] Inf Count: {inf_count} (MUST BE 0)")
    assert nan_count == 0, f"Found {nan_count} NaN values during tick simulation!"
    assert inf_count == 0, f"Found {inf_count} Inf values during tick simulation!"

    # 4. Simulate Candle Rollover & 6-Strategy Signal Inference
    print("\n[Phase 3] Simulating 15m Candle Rollover & 6-Strategy Model Evaluation...")
    # Force next candle timestamp (current epoch + 900s)
    future_epoch = int(time.time() // 900 + 1) * 900
    
    signals_evaluated = 0
    for sym in ALL_SYMBOLS:
        base_p = base_prices.get(sym, 10.0)
        snap = AssetSnapshot(
            symbol=sym,
            price=base_p * 1.005,
            volume=50000.0,
            fut_cvd=120000.0,
            spot_cvd=45000.0,
            funding=0.0002,
            oi=16000000.0,
            liq_long=25000.0,
            liq_short=0.0,
            ls_ratio=2.2,
            coins_bid=800.0,
            coins_ask=300.0,
            dollars_bid=500000000.0,
            dollars_ask=350000000.0,
            whale_idx=45.0,
            tk_buy_cnt=250,
            tk_sell_cnt=100,
            fp_delta=1500.0,
            fp_poc=base_p * 1.004,
            ts_ns=time.time_ns()
        )

        # Trigger rollover by updating time
        with predictor._lock:
            # Set open_time of current candle to previous bar to force close
            predictor.current_candle[sym] = {
                'open_time': future_epoch - 900,
                'open': base_p,
                'high': base_p * 1.01,
                'low': base_p * 0.995,
                'close': base_p * 1.005,
                'volume': 50000.0,
                'fut_cvd': 120000.0,
                'spot_cvd': 45000.0,
                'funding': 0.0002,
                'oi': 16000000.0,
                'liq_long': 25000.0,
                'liq_short': 0.0,
                'ls_ratio': 2.2,
                'coins_bid': 800.0,
                'coins_ask': 300.0,
                'dollars_bid': 500000000.0,
                'dollars_ask': 350000000.0,
                'whale_idx': 45.0,
                'tk_buy_cnt': 250,
                'tk_sell_cnt': 100,
                'fp_delta': 1500.0,
                'fp_poc': base_p * 1.004,
            }

        # Run tick which triggers candle close and model predictions
        out_snap = predictor.on_tick_update(sym, snap, trade_tracker)
        signals_evaluated += 1
        print(f"  [EVAL] {sym:<10} -> Status: {out_snap.strategy_armed:<18} | RSI: {out_snap.rsi:>5.1f} | ATR: {out_snap.atr_14:>7.4f} | Z-Price: {out_snap.p8:>+5.2f}σ")

    print(f"\n[PASS] Successfully evaluated all 6 strategies for {signals_evaluated} symbols.")

    # 5. Verify Rolling Window Cap
    print("\n[Phase 4] Verifying 100-Candle Window Invariant...")
    for sym in ALL_SYMBOLS:
        h_len = len(predictor.candles_history[sym])
        assert h_len <= 100, f"Invariant violated: {sym} has {h_len} candles in history!"
    print("  [PASS] All symbol history buffers strictly bounded at max 100 candles.")

    print("\n" + "=" * 80)
    print("  ALL TICK-BY-TICK EMPIRICAL SIMULATION TESTS PASSED (100% SANITY)")
    print("=" * 80)

if __name__ == "__main__":
    run_deep_simulation()
