"""
Builds the complete DeepSeek-V4 Audit & Simulation Prompt containing full codebases of all Engine_1 core modules.
"""

import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUTPUT_FILE = ROOT / "DEEPSEEK_V4_FULL_CODEBASE_AUDIT_PROMPT.md"

FILES_TO_EMBED = [
    ("Engine_1.py", "Core Multi-Loop Asynchronous Trading Engine, WebSocket Ingestion, SnapshotStore & ANSI Renderer"),
    ("coinglass_scraper.py", "CoinGlass S9 Real-Time Multi-Frame DOM Scraper & CDP Session Manager"),
    ("six_strategy_engine.py", "Machine Learning 6-Strategy Engine, Feature Extraction, Classifiers & Backtester"),
    ("binance_broker.py", "Binance Futures Broker Adapter, Order Execution & Place-Then-Cancel SLTP Guard"),
    ("train_six_strategy.py", "Subprocess Model Retrainer Generating the 84 Strategy Classifier Models"),
    ("run_all_6.py", "20-Window Walk-Forward Backtesting Orchestrator"),
    ("tools/execute_perfect_coinglass_setup.py", "Immutable Playwright Two-Tab Browser Automation & 15m Frame Locker"),
    ("tools/run_autonomous_full_pipeline_simulation.py", "Autonomous End-to-End Line-by-Line Context Simulation Runner")
]

HEADER = """# MASTER DEEPSEEK-V4 FULL CODEBASE SIMULATION & ARCHITECTURAL AUDIT PROMPT

> **TARGET INTELLIGENCE:** DeepSeek-V4 / Arena AI Elite Quantitative Systems Auditor  
> **TASK:** Exhaustive End-to-End Line-by-Line Context Simulation, Concurrency Audit, DOM State Verification, and Risk Governor Certification across the COMPLETE `Engine_1` production codebase.

---

# PART 1: SYSTEM TOPOLOGY & QUANTITATIVE SPECIFICATION

`Engine_1` is an asynchronous quantitative trading engine in Python 3.14 that ingests live order flow and derivatives metrics across 18 assets, evaluates an ensemble of 84 machine learning strategy models, and executes risk-governed perpetual futures orders on Binance.

### 1. Asset Portfolio Matrix (18 Assets)
- **Tab 1 (Port 19899, Profile `chrome_profile_tab1`):** `BTCUSDT`, `ETHUSDT`, `XRPUSDT`, `SOLUSDT`, `BNBUSDT`, `DOGEUSDT`, `ADAUSDT`, `TRXUSDT`, `LINKUSDT`
- **Tab 2 (Port 19900, Profile `chrome_profile_tab2`):** `AVAXUSDT`, `SUIUSDT`, `NEARUSDT`, `DOTUSDT`, `LTCUSDT`, `XAUUSDT`, `XAGUSDT`, `CLUSDT`, `NATGASUSDT`

### 2. Core Operational Constraints & Invariants
1. **15-Minute Resolution Lock (`15m`):** All 18 TradingView chart iframe cells are locked to the `15m` timeframe.
2. **Deterministic Playwright Login:**
   - Navigates to `/login`, fills credentials (`singhkaranbir0248@gmail.com` / `Lu$er2hero`).
   - Clicks `button:has-text('Login')` directly.
   - Awaits deterministic cookie presence (`document.cookie`) with a 5.0-second settlement wait for tokens (`CAUTH`, `cg_auth`, `csrf_token`) to persist.
   - Mounts `/tv/layout/s9`, loads custom layout `L_1`, enforces 15m timeframe, and binds symbol tickers.
3. **SnapshotStore Concurrency:** Updates are serialized via per-symbol `asyncio.Lock`. Read snapshots are immutable (`dataclasses.replace`). ML inference runs outside locks and is throttled to at most 1 evaluation per 2.0s per asset using monotonic clock (`time.monotonic()`).
4. **Risk Governor Invariants:**
   - Zero-naked-window place-then-cancel order updates (`modify_sltp`).
   - UTC calendar day rollover (`time.gmtime()`) resetting daily drawdown baselines at 00:00:00 UTC.
   - Daily maximum drawdown limit (-3.0%) and gross notional exposure cap ($100,000).

---

# PART 2: COMPLETE PRODUCTION CODEBASE (FULL SOURCE)

Below is the complete, untruncated source code for every production file in the `Engine_1` pipeline.

"""

FOOTER = """
# PART 3: AUDIT & SIMULATION DIRECTIVES FOR DEEPSEEK-V4

As the auditing intelligence, execute a complete line-by-line simulation and state analysis addressing:

1. **DOM Locator & Action Simulation:**
   - Trace the exact locator resolution for `button:has-text('Login')` versus `get_by_role("button", name="Login").nth(1)`. Prove why `.first` on text match succeeds on Material-UI buttons with blank sibling icons.
   - Evaluate the impact of the deterministic cookie wait (`document.cookie.includes(...)`) combined with the 5.0-second settlement pause.

2. **Concurrency & Thread Safety Audit:**
   - Audit the per-symbol `asyncio.Lock` mechanism in `SnapshotStore.update()`.
   - Verify that concurrent updates from Binance WebSocket (`price`, `fp_delta`, `fp_poc`) and CoinGlass DOM scrapers (`fut_cvd`, `spot_cvd`, `funding`, `oi`) are serialized without deadlocks or partial field state visibility.
   - Confirm that ML inference dispatch runs outside `self._locks[symbol]` with the 2.0s monotonic throttle.

3. **Risk Governor Mathematical Verification:**
   - Analyze the `modify_sltp` place-then-cancel invariant to verify whether a failure in the Binance API could ever leave a position unhedged (naked window).
   - Verify the UTC standard day integer equation (`int(time.time() // 86400)`) for drawdown baseline rollover at 00:00:00 UTC.

4. **10-Gate Subsystem Rating Scorecard:**
   - Produce a structured markdown table rating each of the 10 subsystems (PASS/FAIL) with mathematical justification.
"""

def generate_prompt():
    out = [HEADER]
    for rel_path, desc in FILES_TO_EMBED:
        fpath = ROOT / rel_path
        if not fpath.exists():
            continue
        print(f"Embedding {rel_path} ({fpath.stat().st_size:,} bytes)...")
        content = fpath.read_text(encoding="utf-8", errors="replace")
        
        section = f"## File: `{rel_path}`\n\n> **Role:** {desc}\n\n```python\n{content}\n```\n\n---\n\n"
        out.append(section)
        
    out.append(FOOTER)
    full_text = "".join(out)
    OUTPUT_FILE.write_text(full_text, encoding="utf-8")
    print(f"Generated {OUTPUT_FILE} ({len(full_text):,} characters / {OUTPUT_FILE.stat().st_size:,} bytes)")

if __name__ == "__main__":
    generate_prompt()
