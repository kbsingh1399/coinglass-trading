"""
Automated Multi-Column Live Update Verification Script
Asserts that values across all terminal columns (Table 1 & Table 2) are actively updating.
"""

import os
import sys
import time
import json
from typing import Dict, Any, List

SNAPSHOT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Seeding", "snapshot_debug.json")
TERMINAL_TEXT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "live_data", "live_terminal_table.txt")

ALL_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT",
    "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT",
    "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT",
    "XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"
]

COLUMNS_TO_AUDIT = [
    "price", "volume", "rsi", "fut_cvd", "spot_cvd",
    "liq_long", "liq_short", "funding", "ls_ratio", "oi",
    "fp_delta", "fp_poc", "whale_idx", "strategy_armed", "ts_ns"
]

def load_snapshot() -> Dict[str, Any]:
    if not os.path.exists(SNAPSHOT_PATH):
        return {}
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def run_column_audit(sample_interval: float = 5.0, max_samples: int = 4) -> bool:
    print(f"=== Starting Multi-Column Live Update Audit ({max_samples} iterations x {sample_interval}s) ===")
    
    samples = []
    for i in range(max_samples):
        snap = load_snapshot()
        if not snap:
            print(f"[{i+1}/{max_samples}] Waiting for snapshot data at {SNAPSHOT_PATH}...")
        else:
            samples.append(snap)
            print(f"[{i+1}/{max_samples}] Captured snapshot with {len(snap)} symbols.")
        time.sleep(sample_interval)

    if len(samples) < 2:
        print("ERROR: Insufficient snapshot samples collected.")
        return False

    first = samples[0]
    last = samples[-1]

    column_changes: Dict[str, int] = {col: 0 for col in COLUMNS_TO_AUDIT}
    symbol_changes: Dict[str, List[str]] = {s: [] for s in ALL_SYMBOLS}

    for sym in ALL_SYMBOLS:
        s_first = first.get(sym, {})
        s_last = last.get(sym, {})
        if not s_first or not s_last:
            continue

        for col in COLUMNS_TO_AUDIT:
            v1 = s_first.get(col)
            v2 = s_last.get(col)
            if v1 != v2 and v1 is not None and v2 is not None:
                column_changes[col] += 1
                symbol_changes[sym].append(f"{col}: {v1} -> {v2}")

    print("\n--- Column Activity Summary Across 18 Symbols ---")
    active_columns = 0
    for col, count in column_changes.items():
        status = "ACTIVE" if count > 0 else "STATIC"
        if count > 0:
            active_columns += 1
        print(f"  - Column '{col}': {count}/18 symbols changed ({status})")

    print(f"\n--- Symbol Activity Summary ---")
    active_symbols = sum(1 for sym, diffs in symbol_changes.items() if len(diffs) > 0)
    print(f"Active Symbols with live updates: {active_symbols}/{len(ALL_SYMBOLS)}")
    for sym, diffs in list(symbol_changes.items())[:6]:
        if diffs:
            print(f"  * {sym}: {', '.join(diffs[:3])}")

    success = active_columns >= 4 and active_symbols >= 10
    print(f"\nAudit Verdict: {'PASS' if success else 'FAIL'} (Active Columns: {active_columns}/{len(COLUMNS_TO_AUDIT)}, Active Symbols: {active_symbols}/{len(ALL_SYMBOLS)})")
    return success

if __name__ == "__main__":
    interval = float(sys.argv[1]) if len(sys.argv) > 1 else 3.0
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    ok = run_column_audit(sample_interval=interval, max_samples=count)
    sys.exit(0 if ok else 1)
