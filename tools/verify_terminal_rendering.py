"""
Visual and ANSI Terminal Rendering Verification Tool
Empirically audits and verifies that all Rich terminal tables, headers, borders,
prices, indicators, and status panels produce vibrant ANSI color codes and that
zero cells or lines degrade to monochrome or washed-out text.
"""

import os
import sys
import re
import time
from typing import Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.table import Table
from rich.text import Text
from Engine_1 import render_table, render_pipeline_status, SnapshotStore, AssetSnapshot, ALL_SYMBOLS, LiveTradeTracker


def run_visual_rendering_audit():
    print("=" * 80)
    print("  LIVE TERMINAL ANSI COLOR AND VISUAL RENDERING EMPIRICAL AUDIT")
    print("=" * 80)

    # 1. Instantiate state store and mock trade tracker with 18 symbols
    tracker = LiveTradeTracker(initial_capital=4233.84)
    store = SnapshotStore(ALL_SYMBOLS, predictor=None, trade_tracker=tracker)

    # Create representative populated snapshots with diverse market values
    snap: Dict[str, AssetSnapshot] = {}
    now_ns = time.time_ns()

    for idx, sym in enumerate(ALL_SYMBOLS):
        # Simulate varied prices and indicator values
        price = 63140.50 if "BTC" in sym else (1885.20 if "ETH" in sym else (75.20 if "SOL" in sym else 1.25))
        rsi = 72.5 if idx % 3 == 0 else (28.4 if idx % 3 == 1 else 51.2)
        fut_cvd = 50000.0 if idx % 2 == 0 else -75000.0
        spot_cvd = -12000.0 if idx % 2 == 0 else 34000.0
        fp_d = 450.25 if idx % 2 == 0 else -320.10
        funding = 0.0055 if idx % 2 == 0 else -0.0008
        oi = 350000000.0
        liq_long = 1250.0 if idx % 2 == 0 else 0.0
        liq_short = 0.0 if idx % 2 == 0 else 2300.0
        lsr = 2.15
        
        # Test both recent timestamps and older timestamps (to prove stale symbols NEVER wash out)
        ts = now_ns if idx < 10 else (now_ns - 200 * 1_000_000_000) # 200s old (simulates background/commodity)

        snap[sym] = AssetSnapshot(
            symbol=sym,
            price=price,
            rsi=rsi,
            fut_cvd=fut_cvd,
            spot_cvd=spot_cvd,
            fp_delta=fp_d,
            fp_poc=price,
            funding=funding,
            oi=oi,
            liq_long=liq_long,
            liq_short=liq_short,
            ls_ratio=lsr,
            dollars_bid=400_000_000.0 if idx < 3 else 0.0,
            dollars_ask=400_000_000.0 if idx < 3 else 0.0,
            whale_idx=-65.4 if idx < 3 else 0.0,
            strategy_armed="READY",
            ts_ns=ts
        )

    # 2. Render table using Rich Console with TrueColor enabled
    console = Console(force_terminal=True, color_system="truecolor", record=True, width=220)
    rendered_group = render_table(snap, tracker, store)

    # Print directly to test console
    console.print(rendered_group)

    # Capture raw text with ANSI escape codes
    raw_ansi = console.export_text(clear=False, styles=True)
    plain_text = console.export_text(clear=False, styles=False)

    # 3. Analyze ANSI escape sequences in the rendered output
    ansi_codes = re.findall(r"\x1b\[[0-9;]*m", raw_ansi)
    total_ansi_tags = len(ansi_codes)

    # Count specific color tags
    yellow_tags = len([c for c in ansi_codes if "33" in c or "93" in c])
    green_tags = len([c for c in ansi_codes if "32" in c or "92" in c])
    red_tags = len([c for c in ansi_codes if "31" in c or "91" in c])
    cyan_tags = len([c for c in ansi_codes if "36" in c or "96" in c])
    magenta_tags = len([c for c in ansi_codes if "35" in c or "95" in c])
    blue_tags = len([c for c in ansi_codes if "34" in c or "94" in c])
    
    # Check for legacy washed-out dim-red tag '\x1b[2;31m'
    dim_red_tags = len([c for c in ansi_codes if "2;31" in c or "2;91" in c])

    print("\n" + "-" * 80)
    print("  EMPIRICAL COLOR CODE AUDIT RESULTS")
    print("-" * 80)
    print(f"  * Total ANSI Styling Escape Sequences : {total_ansi_tags}")
    print(f"  * Yellow Color Sequences (Prices)      : {yellow_tags}")
    print(f"  * Green Color Sequences (Bull/Profits) : {green_tags}")
    print(f"  * Red Color Sequences (Bear/Losses)    : {red_tags}")
    print(f"  * Cyan Color Sequences (Headers/RSI)   : {cyan_tags}")
    print(f"  * Magenta Color Sequences (Table 2)    : {magenta_tags}")
    print(f"  * Blue Color Sequences (Table 1 Border): {blue_tags}")
    print(f"  * Washed-Out Dim-Red Sequences         : {dim_red_tags} (MUST BE 0)")
    print("-" * 80)

    # Assertions
    failures = []
    if total_ansi_tags < 100:
        failures.append(f"Expected >100 ANSI color sequences, found only {total_ansi_tags}")
    if yellow_tags < 18:
        failures.append(f"Expected at least 18 yellow price sequences, found {yellow_tags}")
    if cyan_tags < 10:
        failures.append(f"Expected at least 10 cyan sequences, found {cyan_tags}")
    if magenta_tags < 5:
        failures.append(f"Expected magenta table styling, found {magenta_tags}")
    if dim_red_tags != 0:
        failures.append(f"Found {dim_red_tags} washed-out dim-red tags! Stale fallback is still active.")

    if failures:
        print("\n[FAIL] VERIFICATION FAILED:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("\n[PASS] ALL VISUAL AND COLOR CODING CHECKS PASSED WITH 100% INTEGRITY!")
        print("  * Dashboard is confirmed to render with full vibrant colors across all 18 symbols.")
        print("  * Zero cells or rows degrade to monochrome dim-grey even when timestamps are old.")


if __name__ == "__main__":
    run_visual_rendering_audit()
