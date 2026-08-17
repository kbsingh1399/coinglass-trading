# MISSION: FULL-SCALE ARCHITECTURAL SIMULATION & ADVERSARIAL STRESS-TEST OF ENGINE_1 QUANTITATIVE PIPELINE

## 0. GIT CONTEXT & SYNCHRONIZATION DETAILS

- **Repository:** `https://github.com/kbsingh1399/coinglass-trading`
- **Active Working Branch:** `arena/019fec7a-coinglass-trading`
- **Direct GitHub Branch Link:** https://github.com/kbsingh1399/coinglass-trading/tree/arena%2F019fec7a-coinglass-trading
- **Head Commit Hash:** `78bfb54` (Clean working tree, 100% synchronized with local machine)
- **Recent Commit Trail:**
  - `78bfb54`: `fix(git): remove duplicate lowercase Gemini.md from tracking`
  - `855622f`: `docs: add pipeline analysis prompt, live DOM extraction tools, and rule updates`
  - `7d89c4b`: `feat(engine): sync Binance broker order safety, model retraining updates, and audit verification tools`
  - `f1d9a2f`: `feat(coinglass): restore explicit L_1 layout load in exact user-requested flow order`
  - `17126d0`: `fix(coinglass): remove duplicate goto in inject_and_configure_all to prevent second refresh wiping out setup`
  - `4509175`: `feat(coinglass): remove explicit L_1 layout load to prevent page refresh`

---

## 1. OBJECTIVE

You are tasked with conducting an exhaustive, uncompromising, adversarial audit and full runtime simulation of the **Engine_1 Quantitative Trading Pipeline** (`Engine_1.py`, `binance_broker.py`, `six_strategy_engine.py`, `coinglass_scraper.py`, `tools/extract_live_dom_values.py`).

Your objective is to stress-test every single layer of the pipeline down to millisecond-level race conditions, async deadlocks, browser DOM desynchronization, broker API edge cases, machine learning inference contention, and memory leak vectors.

---

## 2. SYSTEM TOPOLOGY UNDER AUDIT

The pipeline operates across an integrated multi-threaded, asynchronous architecture running 9 concurrent loops:

1. **Dual-Tab Browser Ingestion (Playwright over CDP port 9222 / 19899 / 19900):**
   - 2 persistent Chrome contexts navigating to `https://www.coinglass.com/tv/layout/s9`.
   - Automated layout restoration (`L_1`) and 9-grid frame configuration (`ensure_all_cells_15m`) setting 18 distinct symbols across Tab 1 (BTC, ETH, XRP, SOL, BNB, DOGE, ADA, TRX, LINK) and Tab 2 (AVAX, SUI, NEAR, DOT, LTC, XAU, XAG, CL, NATGAS).
   - Injected JavaScript hooks intercepting XHR/fetch responses and DOM tables.
   - Dual 100ms `poll_loop` instances routing data through `_route_payload` -> `_apply` / `_apply_liq` -> `SnapshotStore.update()`.

2. **Binance Real-Time Stream & REST Ingestion:**
   - `BinanceTradePriceWebSocketFeed`: Persistent WebSocket connection to Binance Futures (`wss://fstream.binance.com/ws/<symbol>@trade`) syncing clock offset with `/fapi/v1/time` and updating real-time tick prices, volume, footprint POC, and delta.
   - `BinanceFootprintFeed`: 5.0-second REST polling cycle for aggregate volume metrics.

3. **State Management & Feature Engine (`SnapshotStore`):**
   - Atomic state container maintaining rolling 100-candle history for 18 assets.
   - Real-time rolling Z-score calculation: `zc4`, `zc10`, `zc20`, `zb4`, `zb10`, `zb20`, `vr`, `zoi`, `zls`, `zfr`.
   - Column staleness tracker highlighting data points unchanged for >60s.

4. **Multi-Threaded Machine Learning Inference:**
   - Dedicated `ML_POOL` (ThreadPoolExecutor with 8 workers).
   - `LiveSixStrategyPredictor` evaluating 6 distinct strategies (S1 to S6) across all 14 traded symbols simultaneously using CatBoost and LightGBM models.
   - Daemon thread `background_retrain_loop` running daily at 00:00 UTC, retraining all 84 model files in an isolated subprocess (`train_six_strategy.py`) without blocking live trading.

5. **Live Trade Execution & Risk Safeguards (`LiveTradeTracker` & `BinanceBrokerAdapter`):**
   - Entry Gate: Validates daily loss limit, maximum simultaneous open positions, and symbol cooldown periods (`_cooldown_secs_after_close`).
   - Order Dispatch: Market order entry with immediate conditional `STOP_MARKET` and `TAKE_PROFIT_MARKET` attachment.
   - Zero-Naked-Window Guard: Verification of Stop Loss placement on exchange before confirming active position.
   - SLTP Modification Guard: Places new Stop Loss first, confirms exchange response, and only then cancels old Stop Loss orders, preventing unhedged exposure during trailing updates.
   - Exit Protocol: Emergency close via Market order, batch deletion of open conditional orders, and immediate realized PnL/fee logging to `Engine_1_trade_logs.json`.

6. **Visual Terminal & Health Watchdogs:**
   - `renderer_loop` (2 Hz / 500ms): Multi-panel Rich ANSI terminal UI export to `live_data/live_terminal_table.txt`.
   - `watchdog` (15s timeout): Checks symbol update timestamps against `STALE_NS` (15s) and triggers automated browser reconnection / iframe re-injection upon scraper stall.
   - `tab_switcher` (5.0s interval): Alternates active window focus between Tab 1 and Tab 2 using `focus_lock` (3.0s timeout) and `bring_to_front` to bypass OS/browser background tab throttling.
   - `rollover_watchdog` (30.0s interval): Handles 00:00 UTC day boundaries and performs non-blocking broker reconciliation against `/fapi/v2/positionRisk`.
   - `event_loop_monitor` (100ms interval): Detects asyncio event loop blocking (>2.0s).
   - Graceful shutdown handler (`sig_handler`) on SIGINT/SIGTERM.

---

## 3. REQUIRED ADVERSARIAL STRESS-TEST SCENARIOS

Perform a deep simulation and analysis across the following scenarios. Provide exact mathematical, structural, and code-level assessments:

### SCENARIO A: Concurrent Focus Contention & Lock Starvation
Simulate the interaction when:
1. `tab_switcher` attempts to acquire `focus_lock` to bring Tab 2 to front.
2. At the exact same microsecond, `watchdog` detects a stale cell in Tab 1 and calls `tab1.reconnect(focus_lock)`.
3. Simultaneously, `tab1.poll_loop` is executing `page.evaluate()` inside an iframe.
- *Questions to answer:* Can a deadlock occur? How does the 3.0s timeout in `tab_switcher` behave? Does `reconnect()` guarantee iframe context invalidation recovery without leaking Chromium target handlers?

### SCENARIO B: Rapid Market Volatility & Binance Order Collision
Simulate an extreme market event (e.g. 5% price candle in 3 seconds across BTC, ETH, SOL):
1. Strategy S1 triggers an Entry while Strategy S4 triggers an Exit on the same symbol.
2. Trailing stop logic calls `modify_sltp()` while Binance API returns `-4130` ("An open stop order exists") or `-4138` ("Order price out of bounds").
3. Network latency causes `/fapi/v1/algoOrder` to timeout after 4.0 seconds.
- *Questions to answer:* How does the new zero-naked-window order flow handle API timeouts? Does the old SL remain active or get prematurely cancelled? How does `reconcile_with_broker()` resolve phantom exchange orders versus local tracker records?

### SCENARIO C: Long-Running Memory Stability (72-Hour Continuous Run)
Simulate a continuous 72-hour execution without restart:
1. Examine `_COLUMN_LAST_VALUES`, `_COLUMN_LAST_CHANGED_TIME`, `_LIVE_LOG_FEED`, `SnapshotStore._history`, `FootprintCandle` buckets, and Playwright CDP event listeners (`_on_response`, `_on_console`).
- *Questions to answer:* Are all internal collections bounded with strict `maxlen` deques or pruning logic? Does `SnapshotStore._run_ml_predictors` create dangling references in `ML_POOL`? Does the Win32 `get_process_memory_usage()` reflect memory leaks in Chrome IPC or Python heap?

### SCENARIO D: Event Loop Responsiveness & ML Inference Backpressure
Simulate tick bursts where all 18 symbols receive WebSocket updates simultaneously at 10 ticks/sec:
1. `SnapshotStore.update()` is called 180 times/second.
2. Each call evaluates whether to dispatch ML prediction tasks to `ML_POOL` (8 worker threads).
- *Questions to answer:* Does the task submission saturate `ML_POOL` queue? Does `asyncio.to_thread` or thread pool task scheduling induce event loop jitter that delays the 2 Hz `renderer_loop` or the 100ms `poll_loop`?

### SCENARIO E: Scraper Deadlock & Anti-Bot Challenge Resilience
Simulate CoinGlass website refreshing, displaying a Cloudflare challenge, or iframe DOM structures mutating dynamically:
1. Iframe element selectors `#tv_chart_container_win1 iframe` fail to resolve.
2. `page.evaluate()` inside `poll_loop` throws `Execution context was destroyed`.
- *Questions to answer:* Trace the exact recovery path through `watchdog -> reconnect -> inject_and_configure_all -> ensure_all_cells_15m`. What is the maximum recovery time before data resumes flowing?

---

## 4. EXPECTED OUTPUT FORMAT

Produce a comprehensive, structured evaluation containing:
1. **Critical Vulnerability Findings:** Any potential deadlock, race condition, naked position window, or memory leak identified, ranked by severity (CRITICAL, HIGH, MEDIUM, LOW).
2. **Step-by-Step Simulation Trace:** Detailed execution walk-through for Scenarios A through E with failure modes and mitigations.
3. **Architectural Hardening Recommendations:** Specific, high-impact code optimizations to maximize reliability, eliminate latency, and guarantee 100% operational uptime.
