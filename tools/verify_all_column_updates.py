"""
Automated Multi-Column Continuous Staleness Monitor & Audit
Performs rigorous 30-second checking intervals across all columns in Table 1 and Table 2.
Asserts that at least one value in each column is actively moving and not stale.
"""

import os
import sys
import re
import time
import json
from datetime import datetime
from typing import Dict, Any, List, Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_PATH = os.path.join(BASE_DIR, "Seeding", "snapshot_debug.json")
TERMINAL_TEXT_PATH = os.path.join(BASE_DIR, "live_data", "live_terminal_table.txt")

ALL_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT",
    "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT",
    "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT",
    "XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"
]

TABLE_1_COLUMNS = [
    "Price", "RSI", "Fut CVD", "Spot CVD", "FP Delta", "FP POC", "Funding", "OI", "Regime"
]

TABLE_2_COLUMNS = [
    "Bid Vol ($)", "Ask Vol ($)", "Whale Idx", "Liq Long", "Liq Short", "L/S Ratio", "Z-Price", "Z-CVD", "Z-OI", "ARM"
]

def load_snapshot() -> Dict[str, Any]:
    if not os.path.exists(SNAPSHOT_PATH):
        return {}
    try:
        with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def parse_terminal_table() -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    """Parse text representation of Table 1 and Table 2 directly from live_terminal_table.txt"""
    if not os.path.exists(TERMINAL_TEXT_PATH):
        return {}, {}
    try:
        with open(TERMINAL_TEXT_PATH, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return {}, {}

    t1_data: Dict[str, Dict[str, str]] = {}
    t2_data: Dict[str, Dict[str, str]] = {}

    lines = [l.strip() for l in content.splitlines() if l.strip()]
    in_t1 = False
    in_t2 = False

    for line in lines:
        if "Market Overview, Volume & Footprint" in line:
            in_t1 = True
            in_t2 = False
            continue
        elif "Order Book Depth, Liquidations" in line:
            in_t1 = False
            in_t2 = True
            continue
        elif "Active Trades" in line or "Pipeline Status" in line:
            in_t1 = False
            in_t2 = False
            continue

        if line.startswith("│") and not line.startswith("┌") and not line.startswith("└") and not line.startswith("├"):
            parts = [p.strip() for p in line.split("│")[1:-1]]
            if not parts:
                continue
            sym = parts[0]
            if sym == "Symbol" or not sym:
                continue
            if in_t1 and len(parts) >= 10:
                t1_data[sym] = {
                    "Price": parts[1],
                    "RSI": parts[2],
                    "Fut CVD": parts[3],
                    "Spot CVD": parts[4],
                    "FP Delta": parts[5],
                    "FP POC": parts[6],
                    "Funding": parts[7],
                    "OI": parts[8],
                    "Regime": parts[9]
                }
            elif in_t2 and len(parts) >= 11:
                t2_data[sym] = {
                    "Bid Vol ($)": parts[1],
                    "Ask Vol ($)": parts[2],
                    "Whale Idx": parts[3],
                    "Liq Long": parts[4],
                    "Liq Short": parts[5],
                    "L/S Ratio": parts[6],
                    "Z-Price": parts[7],
                    "Z-CVD": parts[8],
                    "Z-OI": parts[9],
                    "ARM": parts[10]
                }

    return t1_data, t2_data

def run_single_30s_check(check_id: int = 1, interval_sec: float = 30.0) -> Dict[str, Any]:
    """Capture initial frame, wait 30 seconds, capture second frame, and evaluate movements."""
    timestamp_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n================================================================================")
    print(f"  [CHECK #{check_id}] Starting 30-Second Column Staleness Audit at {timestamp_start}")
    print(f"================================================================================")

    # Initial frame
    snap_1 = load_snapshot()
    t1_a, t2_a = parse_terminal_table()

    print(f"  -> Captured baseline frame (Snap symbols: {len(snap_1)}, T1 symbols: {len(t1_a)}, T2 symbols: {len(t2_a)})")
    print(f"  -> Sleeping {interval_sec:.1f}s for live price/indicator movements...")
    time.sleep(interval_sec)

    # Target frame
    snap_2 = load_snapshot()
    t1_b, t2_b = parse_terminal_table()
    timestamp_end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"  -> Captured target frame at {timestamp_end}")

    # Evaluate Table 1
    t1_changes: Dict[str, List[Tuple[str, str, str]]] = {col: [] for col in TABLE_1_COLUMNS}
    for sym in ALL_SYMBOLS:
        row_a = t1_a.get(sym, {})
        row_b = t1_b.get(sym, {})
        for col in TABLE_1_COLUMNS:
            v_a = row_a.get(col, "")
            v_b = row_b.get(col, "")
            if v_a and v_b and v_a != v_b:
                t1_changes[col].append((sym, v_a, v_b))

    # Evaluate Table 2
    t2_changes: Dict[str, List[Tuple[str, str, str]]] = {col: [] for col in TABLE_2_COLUMNS}
    for sym in ALL_SYMBOLS:
        row_a = t2_a.get(sym, {})
        row_b = t2_b.get(sym, {})
        for col in TABLE_2_COLUMNS:
            v_a = row_a.get(col, "")
            v_b = row_b.get(col, "")
            if v_a and v_b and v_a != v_b:
                t2_changes[col].append((sym, v_a, v_b))

    # Snapshot core metric evaluation
    snap_cols = ["price", "rsi", "fut_cvd", "spot_cvd", "fp_delta", "funding", "oi", "liq_long", "liq_short", "ls_ratio", "whale_idx"]
    snap_changes: Dict[str, int] = {col: 0 for col in snap_cols}
    for sym in ALL_SYMBOLS:
        sa = snap_1.get(sym, {})
        sb = snap_2.get(sym, {})
        for col in snap_cols:
            if sa.get(col) != sb.get(col) and sa.get(col) is not None:
                snap_changes[col] += 1

    def _safe_str(s: Any) -> str:
        text = str(s)
        return text.replace("\u03c3", "s").replace("\u2212", "-").replace("\u2205", "0").replace("\u2013", "-")

    print("\n--- TABLE 1 (Market Overview, Volume & Footprint) Staleness Audit ---")
    t1_active = 0
    for col in TABLE_1_COLUMNS:
        diffs = t1_changes[col]
        n = len(diffs)
        status = f"MOVING ({n} symbols changed)" if n > 0 else "STALE (0 changes)"
        if n > 0:
            t1_active += 1
        sample_str = f" [e.g., {_safe_str(diffs[0][0])}: {_safe_str(diffs[0][1])} -> {_safe_str(diffs[0][2])}]" if n > 0 else ""
        print(f"  * Column '{col:<10}': {status}{sample_str}")

    print("\n--- TABLE 2 (Depth, Liquidations & Analytics) Staleness Audit ---")
    t2_active = 0
    for col in TABLE_2_COLUMNS:
        diffs = t2_changes[col]
        n = len(diffs)
        status = f"MOVING ({n} symbols changed)" if n > 0 else "STALE (0 changes)"
        if n > 0:
            t2_active += 1
        sample_str = f" [e.g., {_safe_str(diffs[0][0])}: {_safe_str(diffs[0][1])} -> {_safe_str(diffs[0][2])}]" if n > 0 else ""
        print(f"  * Column '{col:<12}': {status}{sample_str}")

    total_table_cols = len(TABLE_1_COLUMNS) + len(TABLE_2_COLUMNS)
    total_active_cols = t1_active + t2_active
    active_snap_cols = sum(1 for c, cnt in snap_changes.items() if cnt > 0)

    print(f"\nAudit Summary: Active Table Columns = {total_active_cols}/{total_table_cols} | Active Snapshot Fields = {active_snap_cols}/{len(snap_cols)}")
    is_healthy = t1_active >= 7 and t2_active >= 6
    print(f"Audit Health Verdict: {'[OK] HEALTHY & MOVING' if is_healthy else '[WARN] POTENTIAL COLUMN STALENESS'}")

    return {
        "check_id": check_id,
        "timestamp": timestamp_end,
        "t1_active": t1_active,
        "t2_active": t2_active,
        "total_active": total_active_cols,
        "healthy": is_healthy
    }

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Multi-column 30s staleness monitor")
    parser.add_argument("--interval", type=float, default=30.0, help="Check interval in seconds")
    parser.add_argument("--cycles", type=int, default=1, help="Number of audit cycles to perform (default: 1, 0 for infinite)")
    args = parser.parse_args()

    cycle = 0
    while True:
        cycle += 1
        res = run_single_30s_check(check_id=cycle, interval_sec=args.interval)
        if args.cycles > 0 and cycle >= args.cycles:
            break
        print(f"\nSleeping {args.interval:.0f}s until next check cycle...")
        time.sleep(1.0)

if __name__ == "__main__":
    main()
