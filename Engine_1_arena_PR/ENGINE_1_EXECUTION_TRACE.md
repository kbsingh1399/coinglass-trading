# Engine_1.py — Step-by-Step Execution Trace

Use this guide to verify each phase in your logs. Every `print()` statement is listed in the exact order it fires.

---

## PHASE 0: Module Import (Top-Level Code)

Fires immediately when `python3 Engine_1.py` is run, before `main()` starts.

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 0.1 | `[Setup] Successfully loaded feature prep function for {ACTIVE_STRATEGY}.` | 115 | Legacy feature prep loaded (harmless) |
| 0.2 | `[Setup] [ERROR] Could not load prep function for {ACTIVE_STRATEGY}: ...` | 117 | Only if legacy prep fails (non-blocking) |

**What to verify:** You should see `0.1` or `0.2` (one of them). This is legacy code and doesn't affect the six-strategy pipeline.

---

## PHASE 1: System Startup Banner

First thing printed inside `main()`.

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 1.1 | `============================================================` | 3573 | Banner start |
| 1.2 | `  SYSTEM STARTUP - MODE: LIVE (METATRADER 5)` | 3574 | Execution mode (from `EXECUTION_MODE` env var) |
| 1.3 | `  TRADES ARE DISPATCHED TO METATRADER 5 BROKER / LOCAL TRACKER` | 3576 | If `MT5_LIVE=1` (real trading) |
| 1.4 | `  WARNING: NO REAL METATRADER 5 TRADE ORDERS WILL BE SENT` | 3578 | If `MT5_LIVE=0` (paper trading) |
| 1.5 | `  TRADES ARE SIMULATED LOCALLY IN THE TRACKER FILE` | 3579 | If `MT5_LIVE=0` (paper trading) |
| 1.6 | `============================================================` | 3580 | Banner end |

**What to verify:** You should see `1.2` with your mode. If paper trading, you'll see `1.4` and `1.5`.

---

## PHASE 2: ML Model Retraining (Boot-Time)

Trains the 84 six-strategy models before anything else starts.

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 2.1 | `[Setup] Skipping initial ML model retraining (--skip-train passed). Using existing models.` | 3587 | Only if `--skip-train` flag passed |
| 2.2 | `[Setup] Clearing existing ML model files before retraining...` | 3589 | Clears old model files |
| 2.3 | `[Setup] [WARN] Could not remove old model file {file}: ...` | 3595 | Only if file deletion fails |
| 2.4 | `[Setup] Running Live Model Retraining on latest Parquet data...` | 3598 | Training starts |
| 2.5 | `[Setup] Training Six-Strategy ML models (S1-S6 × 14 symbols)...` | 3609 | Importing trainer |

### 2a. Training Sub-Phase (train_six_strategy.py output)

These print inside `train_all_strategies()`:

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 2a.1 | `======================================================================` | 324 | Training banner |
| 2a.2 | `SIX-STRATEGY ML MODEL TRAINER` | 325 | |
| 2a.3 | `Data directory: backtesting_data` | 327 | |
| 2a.4 | `Model directory: six_strategy_models` | 328 | |
| 2a.5 | `Symbols: 14` | 329 | |
| 2a.6 | `Strategies: 6` | 330 | |
| 2a.7 | `[1/3] Loading BTC reference data...` | 334 | Loading BTC data |
| 2a.8 | `  BTC: {N} bars loaded` | 342 | BTC loaded (expect ~231K bars) |
| 2a.9 | `[2/3] Training models...` | 346 | Training loop starts |
| 2a.10 | `STRATEGY: S1_Liquidation` | 355 | First strategy |
| 2a.11 | `  BTCUSDT: Training ({N} trades, {W} wins)... ✓ Saved ({F} features, WR={X}%)` | 398-426 | Model trained |
| 2a.12 | `  ETHUSDT: Training ...` | 398 | Next symbol |
| ... | *(repeats for all 14 symbols × 6 strategies)* | | |
| 2a.13 | `  S1_Liquidation: 14/14 models trained` | 434 | Strategy complete |
| 2a.14 | `STRATEGY: S2_CVD_Momentum` | 355 | Next strategy |
| ... | *(repeats for S2-S6)* | | |
| 2a.15 | `[3/3] TRAINING COMPLETE` | 440 | All done |
| 2a.16 | `  Total models trained: 84/84` | 442 | **Verify: 84/84** |
| 2a.17 | `  Skipped: 0` | 443 | **Verify: 0 skipped** |
| 2a.18 | `✓ Models ready for live trading!` | 448 | Success |

**What to verify:** Look for `Total models trained: 84/84` and `Skipped: 0`. This takes ~15 minutes.

### 2b. Back to Engine_1.py

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 2.6 | `[Setup] ✓ Six-Strategy models trained successfully` | 3610 | Training returned OK |
| 2.7 | `[Setup] [WARN] Failed to retrain Six-Strategy models: ...` | 3612 | Only if training crashes |

**What to verify:** You should see `2.6`. If you see `2.7`, training failed — check the traceback.

---

## PHASE 3: Six-Strategy Predictor Initialization

Loads the 84 trained models into memory.

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 3.1 | `[SixStrategy] Loaded 84 models across 6 strategies` | 430 | **CRITICAL: Verify 84 models loaded** |
| 3.2 | `[SixStrategy] No pre-trained models at six_strategy_models — will train on first data` | 412 | **ERROR: Models not found!** |
| 3.3 | `[SixStrategy] Loaded history for {N} symbols from disk cache.` | 485 | Historical candles loaded |
| 3.4 | `[SixStrategy] No combined seeding file at ...` | 457 | No disk cache (first run) |
| 3.5 | `[Setup] Six-Strategy Predictor initialized with {N} model sets` | 3622 | **Verify: N=6 (one dict per strategy)** |

**What to verify:** You MUST see `3.1` with "84 models". If you see `3.2`, the models weren't trained or the directory is wrong.

---

## PHASE 4: Background Retraining Thread

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 4.1 | `[Setup] Launched 24hr Background Retraining Manager Thread (Process-isolated).` | 3689 | Thread started |
| 4.2 | `[Background Thread] Launching 24hr Live Retraining Subprocess...` | 3680 | Fires every 24 hours |
| 4.3 | `[Background Process] Starting Live Retraining for Six-Strategy models...` | 3633 | Subprocess started |
| 4.4 | `[Background Process] ✓ Six-Strategy retraining completed` | 3637 | Success |
| 4.5 | `[Background Process] Six-Strategy retrain failed: ...` | 3639 | Only on failure |

**What to verify:** You should see `4.1` at startup. `4.2`-`4.5` fire every 24 hours.

---

## PHASE 5: MT5 Broker Connection

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 5.1 | `[MT5] Connected to MetaTrader 5 successfully!` | 65 | **CRITICAL: MT5 connected** |
| 5.2 | `[MT5] initialize() failed (attempt {N}), error=...` | 60 | MT5 connection failed |
| 5.3 | `[MT5] Connection lost or mock environment. Re-initializing...` | 81 | Reconnection attempt |

**What to verify:** You should see `5.1`. If you see `5.2`, MT5 isn't available (expected on Linux without Wine/MT5).

---

## PHASE 6: Chromium Browser Launch

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 6.1 | `[Setup] Launching Chromium instance with persistent profile...` | 3694 | Browser starting |
| 6.2 | `[Setup] Navigating to Coinglass Login...` | 3732 | Opening login page |
| 6.3 | `[Setup] Submitting login form...` | 3767 | Auto-login (if env vars set) |
| 6.4 | `[Setup] Waiting for post-login redirect...` | 3790 | Waiting for login success |
| 6.5 | `[Setup] Login successful — redirected away from /login.` | 3793 | Login OK |
| 6.6 | `[Setup] [WARN] No redirect detected — may already be logged in or login failed.` | 3795 | Login ambiguous |
| 6.7 | `[Setup] Waiting 5 seconds to ensure session cookies are fully persisted...` | 3797 | Cookie warmup |
| 6.8 | `[Setup] Form inputs not detected, assuming session already active.` | 3800 | Already logged in |
| 6.9 | `[Setup] COINGLASS_EMAIL or COINGLASS_PASSWORD environment variables not set — skipping automated web login.` | 3756 | No credentials |
| 6.10 | `[Setup] [WARN] Login navigation attempt {N} failed: ...` | 3742 | Navigation retry |

**What to verify:** You should see `6.1` → `6.2` → either `6.5`/`6.8` (success) or `6.9` (no credentials). The system uses persistent browser profiles, so if you've logged in before, it may skip straight to `6.8`.

---

## PHASE 7: Coinglass Tab Setup

Two CoinglassTab instances (TAB_1, TAB_2) are created and configured.

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 7.1 | `[TAB_1] Opening layout: https://www.coinglass.com/tv/layout/s9...` | 2510 | Tab 1 opening |
| 7.2 | `[TAB_1] Waiting 15 seconds for layout to load...` | 2512 | Waiting for page |
| 7.3 | `[TAB_2] Opening layout: ...` | 2510 | Tab 2 opening |
| 7.4 | `[TAB_2] Waiting 15 seconds for layout to load...` | 2512 | Waiting for page |
| 7.5 | `[TAB_1] Bringing tab to front...` | 2537 | Focusing tab |
| 7.6 | `[TAB_1] Waiting for layout containers to render...` | 2543 | DOM ready |
| 7.7 | `[TAB_1] Configuring symbols and indicators on grid layout via JS API...` | 2550 | Injecting config |
| 7.8 | `[TAB_1] [Config] Configuring window {N}/9 for {symbol}` | 2552 | Per-window setup |
| 7.9 | `[TAB_1] [Config] Symbol & Indicators verified/configured for {symbol}` | 2565 | Window OK |
| 7.10 | `[TAB_1] [WARN] Programmatic setup failed for {symbol}: ...` | 2563 | Window failed |
| 7.11 | `[TAB_1] Waiting 15 seconds for TradingView studies to load historical data...` | 2571 | Studies loading |
| 7.12 | `[TAB_1] Setup & Indicator injection complete.` | 2578 | Tab 1 ready |
| 7.13 | *(same sequence for TAB_2)* | | Tab 2 ready |

**What to verify:** You should see `7.12` for both tabs. If you see `7.10`, some windows failed to configure.

---

## PHASE 8: Historical Seeding

Scrolls through historical data on each Coinglass chart window and saves to Excel.

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 8.1 | `[Setup] --skip-seed flag active. Skipping historical seeding.` | 3798 | Only if `--skip-seed` |
| 8.2 | `[Setup] Launching historical seeding...` | 3827 | Seeding starts |
| 8.3 | `[TAB_1] Seeding BTCUSDT in Window 1. Acquired focus lock. Bringing tab to front...` | 2823 | Per-symbol seeding |
| 8.4 | `[TAB_1] waiting for indicators to populate historical data for BTCUSDT...` | 2882 | Data loading |
| 8.5 | `[TAB_1] Indicators populated in {X}s` | 2892 | Data ready |
| 8.6 | `[TAB_1] Seeding BTCUSDT: candle {N}/{target}...` | 2990 | Scroll progress |
| 8.7 | *(repeats for all symbols on both tabs)* | | |
| 8.8 | `[Setup] Seeding phase complete! Starting real-time feeds...` | 3829 | Seeding done |
| 8.9 | `[Setup] Combining {N} seeding files into a single workbook...` | 3525 | Merging Excels |
| 8.10 | `[Setup] Combined workbook saved successfully: combined_seed_history.xlsx` | 3562 | Merged file saved |
| 8.11 | `[Setup] Cleaned up individual symbol seeding files.` | 3567 | Cleanup done |

**What to verify:** You should see `8.8` after all symbols are seeded. This can take 30-60 minutes depending on data depth. If `--skip-seed`, you'll see `8.1` and skip to Phase 9.

---

## PHASE 9: Live Feeds Start (asyncio.gather)

All real-time data feeds launch simultaneously.

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 9.1 | `[Binance WS] Starting with URL: wss://fstream.binance.com/stream?streams=...` | 2167 | WebSocket connecting |
| 9.2 | `[Binance WS] Connected trade price stream.` | 2179 | **CRITICAL: WS connected** |
| 9.3 | `[Binance WS] Disconnected/error: ... Reconnecting in 5s...` | 2224 | WS error (auto-reconnects) |
| 9.4 | `[Binance Feed] [INFO] Connection restored.` | 2291 | REST feed recovered |
| 9.5 | `[Binance Feed] [WARN] Connection issues detected (all queries failed).` | 2297 | REST feed down |
| 9.6 | `[Binance Feed] [WARN] Session error: ... Retrying in 10s...` | 2305 | REST retry |

**What to verify:** You should see `9.2` (WebSocket connected). The Binance Footprint REST feed runs silently unless there's an error.

---

## PHASE 10: Runtime — Continuous Operation

These messages fire repeatedly during live trading.

### 10a. Coinglass Polling (every ~15 seconds per tab)

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 10a.1 | `[TAB_1] [POLL ERROR] {sym} frame eval: ...` | 2696 | Frame read failed |
| 10a.2 | `[TAB_1] [POLL ERROR] Subtask failed: ...` | 2741 | Poll subtask error |
| 10a.3 | `[TAB_1] [POLL ERROR] Outer: ...` | 2752 | Poll loop error |
| 10a.4 | `[TAB_1] [WATCHDOG] Max failures exceeded ({N}). Auto-healing by reloading page...` | 2756 | Auto-recovery triggered |
| 10a.5 | `[TAB_1 CONSOLE] {typ} {text}` | 2480 | Browser console messages |
| 10a.6 | `[TAB_1 PAGE ERROR] {msg}` | 2487 | JavaScript errors |

**What to verify:** During normal operation, you should NOT see these. If you see `10a.4`, the tab auto-healed. Occasional `10a.5`/`10a.6` are normal browser noise.

### 10b. ML Prediction (every 15-minute candle close)

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 10b.1 | `[SixStrategy] {symbol} error: ...` | 621 | Prediction crashed for a symbol |

**What to verify:** During normal operation, you should NOT see `10b.1`. The predictor runs silently — it only prints on errors.

### 10c. Trade Dispatch (when a signal fires)

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 10c.1 | `[RiskGovernor] Entry blocked. Symbol={sym} Strategy={strat}. Emergency halt active.` | 1618 | Emergency halt |
| 10c.2 | `[RiskGovernor] Entry blocked. Symbol={sym} Strategy={strat}. Daily drawdown ({X}%) exceeds 4% guardrail.` | 1629 | Daily DD limit |
| 10c.3 | `[RiskGovernor] Entry blocked. Symbol={sym} Strategy={strat}. Total drawdown ({X}%) exceeds 8% guardrail.` | 1635 | Total DD limit |
| 10c.4 | `[RiskGovernor] Entry blocked by cooldown. Symbol={sym} Strategy={strat} Remaining={N}s` | 1641 | Re-entry cooldown |
| 10c.5 | `[RiskGovernor] Entry blocked. Symbol={sym} Strategy={strat}. Total portfolio stop risk (${X}) exceeds 4% of equity (${Y}).` | 1683 | Portfolio risk limit |
| 10c.6 | `[TradeTracker] MT5 rejected {sym} ({strat}) - removing phantom trade.` | 1721 | MT5 rejected order |

**What to verify:** If a trade is blocked, you'll see one of `10c.1`-`10c.6` explaining why. If a trade goes through, you'll see MT5 prints below.

### 10d. MT5 Execution (when a trade is dispatched)

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 10d.1 | `[MT5 DRY RUN] {sym} \| LONG/SHORT` | 296 | Paper trade logged |
| 10d.2 | `   Engine Entry: {price} \| MT5 Entry/Exec: {price}` | 297 | Entry prices |
| 10d.3 | `   Basis: {X}% \| Allowed: {Y}%` | 298 | Basis check |
| 10d.4 | `   MT5 SL: {price} \| MT5 TP: {price}` | 299 | SL/TP levels |
| 10d.5 | `   Lot: {N} \| Risk: ${X} \| dev={N}pts` | 300 | Position sizing |
| 10d.6 | `[MT5] Order placed successfully ...` | 368 | **Trade executed** |
| 10d.7 | `[MT5 SKIP] {sym}: symbol_info unavailable.` | 192 | Symbol not on MT5 |
| 10d.8 | `[MT5 SKIP] {sym}: no live tick.` | 197 | No price data |
| 10d.9 | `[MT5 SKIP] order_check failed: retcode={N}, comment=...` | 333 | Pre-check failed |
| 10d.10 | `[MT5] Order failed after retries. Code={N}, Comment=...` | 340 | Order failed |

**What to verify:** In paper mode (`MT5_LIVE=0`), you'll see `10d.1`-`10d.5`. In live mode, you'll see `10d.6` on success or `10d.10` on failure.

### 10e. Trade Exits (SL/TP/Trail hit)

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 10e.1 | `[MT5] Close rejected/failed for {t_id}. Re-arming local state.` | 1930 | Close failed |
| 10e.2 | `[MT5] Exception during async close for {t_id}: ...` | 1933 | Close error |
| 10e.3 | `[MT5 DRY RUN] Modify SLTP {sym} ticket={N} SL={price} TP={price}` | 388 | Trailing stop updated |
| 10e.4 | `[MT5] SLTP modify failed. Code={N}, Comment=...` | 416 | SL/TP modify failed |

**What to verify:** In paper mode, exits are handled locally. In live mode, you'll see `10e.3` for trailing stop updates.

### 10f. Risk Governor (continuous monitoring)

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 10f.1 | `[RiskGovernor] Daily starting capital rolled over to ${X} at Athens server day {N}` | 1613 | Day rollover |
| 10f.2 | `[RiskGovernor] [CRITICAL] EMERGENCY HALT TRIGGERED! Daily DD={X}%, Total DD={Y}%. Closing all active trades.` | 1777 | **CRITICAL: All trades closed** |

**What to verify:** `10f.1` fires once per day. `10f.2` should NEVER fire in normal operation.

### 10g. Tab Switcher (every 60 seconds)

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 10g.1 | `[Switcher] Warning: focus_lock timeout. Bypassing lock...` | 3852 | Lock contention |
| 10g.2 | `[Switcher] Failed to switch to {tab}: ...` | 3858 | Switch failed |

**What to verify:** Normally silent. Occasional `10g.1` is harmless.

### 10h. Watchdog (continuous)

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 10h.1 | `[Watchdog] [WARN] Subsystem '{name}' hung. Heartbeat silent >90s.` | 3483 | Feed stopped |
| 10h.2 | `[Watchdog] [RECOVERY] Attempting recovery for '{tab_id}'...` | 3485 | Auto-recovery |
| 10h.3 | `[Watchdog] [ERROR] Recovery failed for '{tab_id}': ...` | 3501 | Recovery failed |
| 10h.4 | `[Watchdog] [ALERT] [MEMORY] Python memory usage is extremely high ({X} MB)!` | 3504 | Memory pressure |
| 10h.5 | `[Watchdog] [ERROR] Rollover watchdog failed: ...` | 3862 | Watchdog error |

**What to verify:** Normally silent. `10h.1`-`10h.3` indicate a feed crashed and was recovered.

### 10i. Latency Monitor (continuous)

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 10i.1 | `[ALERT] [LAG] WebSocket message processing lag for {sym} is {X}s!` | 2210 | WS lag detected |
| 10i.2 | `[ALERT] [LATENCY] Event loop blocked for {X}s!` | 3873 | Event loop blocked |
| 10i.3 | `[Watchdog] [ALERT] [LATENCY_CRITICAL] Event loop blocked consecutively 5 times. Process is hung.` | 3875 | **CRITICAL: Process hung** |

**What to verify:** Normally silent. Occasional `10i.1` is acceptable. `10i.3` means the process is frozen.

### 10j. MT5 Sync (every 30 seconds)

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 10j.1 | `[MT5 SYNC] Removed orphaned local trade {tid} (ticket={ticket})` | 2172 | Stale trade cleaned |
| 10j.2 | `[MT5 SYNC] reconcile error: ...` | 2179 | Sync failed |

**What to verify:** Normally silent. `10j.1` fires if MT5 closed a position that the tracker didn't know about.

---

## PHASE 11: Shutdown

| # | Log Message | Line | What It Means |
|---|-------------|------|---------------|
| 11.1 | `[Exit] Termination signal received. Stopping...` | 3892 | Ctrl+C or SIGTERM |
| 11.2 | `[Setup] Cleaning up tasks and closing browser...` | 3910 | Cleanup started |
| 11.3 | `[Exit] Shutdown complete.` | 3917 | **Clean exit** |

**What to verify:** You should see `11.3` on clean shutdown.

---

## Quick Reference: What You SHOULD See on a Healthy Run

```
============================================================
  SYSTEM STARTUP - MODE: LIVE (METATRADER 5)
  WARNING: NO REAL METATRADER 5 TRADE ORDERS WILL BE SENT
  TRADES ARE SIMULATED LOCALLY IN THE TRACKER FILE
============================================================
[Setup] Running Live Model Retraining on latest Parquet data...
[Setup] Training Six-Strategy ML models (S1-S6 × 14 symbols)...
  ... (training output for 84 models) ...
  Total models trained: 84/84
  Skipped: 0
✓ Models ready for live trading!
[Setup] ✓ Six-Strategy models trained successfully
[SixStrategy] Loaded 84 models across 6 strategies
[SixStrategy] Loaded history for 14 symbols from disk cache.
[Setup] Six-Strategy Predictor initialized with 6 model sets
[Setup] Launched 24hr Background Retraining Manager Thread (Process-isolated).
[MT5] Connected to MetaTrader 5 successfully!
[Setup] Launching Chromium instance with persistent profile...
[Setup] Navigating to Coinglass Login...
[Setup] Login successful — redirected away from /login.
[TAB_1] Opening layout: https://www.coinglass.com/tv/layout/s9...
[TAB_1] Setup & Indicator injection complete.
[TAB_2] Opening layout: https://www.coinglass.com/tv/layout/s9...
[TAB_2] Setup & Indicator injection complete.
[Setup] Launching historical seeding...
  ... (seeding output for all symbols) ...
[Setup] Seeding phase complete! Starting real-time feeds...
[Binance WS] Starting with URL: wss://fstream.binance.com/stream?streams=...
[Binance WS] Connected trade price stream.
  ... (runtime — silent unless errors or trades fire) ...
```

---

## Quick Reference: Red Flags to Watch For

| Log Message | Severity | Action |
|-------------|----------|--------|
| `[SixStrategy] No pre-trained models` | 🔴 CRITICAL | Run `python3 train_six_strategy.py` manually |
| `[MT5] initialize() failed` | 🟡 WARNING | MT5 not available (OK on Linux without Wine) |
| `[Binance WS] Disconnected/error` | 🟡 WARNING | Auto-reconnects in 5s |
| `[TAB_1] [WATCHDOG] Max failures exceeded` | 🟡 WARNING | Tab auto-heals by reloading |
| `[RiskGovernor] [CRITICAL] EMERGENCY HALT` | 🔴 CRITICAL | All trades closed — investigate drawdown |
| `[ALERT] [LATENCY_CRITICAL]` | 🔴 CRITICAL | Process is hung — restart |
| `[MT5] Order failed after retries` | 🟡 WARNING | Check MT5 connection and symbol availability |
| `[RiskGovernor] Entry blocked` | ℹ️ INFO | Normal risk management — trade was filtered |

---

**Document Version:** 2026-08-12  
**Engine_1.py Commit:** 87d3493  
**Total Lines:** 3,925 (Engine_1.py) + 674 (six_strategy_engine.py) + 465 (train_six_strategy.py)
