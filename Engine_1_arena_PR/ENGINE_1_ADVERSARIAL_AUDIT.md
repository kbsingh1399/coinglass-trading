# Engine_1 Quantitative Pipeline — Full-Scale Adversarial Stress-Test Audit

**Audit Date:** 2026-08-17  
**Branch:** `arena/019fec7a-coinglass-trading`  
**Files Audited:** `Engine_1.py` (2767 lines), `engine_components/coinglass_scraper.py` (1803 lines), `engine_components/binance_broker.py` (759 lines), `engine_components/mt5_broker.py` (553 lines), `six_strategy_engine.py` (674 lines)

---

## CRITICAL VULNERABILITY FINDINGS

### Finding 1: NAKED POSITION WINDOW During Binance SL/TP Modification
**Severity:** CRITICAL  
**Location:** `engine_components/binance_broker.py` L462-487 (`modify_sltp`)

```python
# Cancel ALL existing algo orders first
open_algos = self._request("GET", "/fapi/v1/openAlgoOrders", ...)
for algo in open_algos:
    self._request("DELETE", "/fapi/v1/algoOrder", ...)  # OLD SL CANCELLED HERE

# ── NAKED WINDOW: ~1-5 seconds with NO stop-loss on exchange ──

# Place new SL first
new_sl_res = self._place_algo_conditional(...)  # NEW SL PLACED HERE
if not new_sl_res:
    self.close_position(...)  # Emergency close, but damage may be done
```

**Impact:** Between cancelling the old SL and placing the new SL, the position is completely unprotected on the exchange. A flash crash during this 1-5 second window results in unlimited loss. The emergency `close_position()` fires only AFTER the new SL placement fails, adding another 1-3 seconds of naked exposure.

**Mitigation Required:** Implement a place-then-cancel pattern: place the new SL first, confirm it exists, then cancel the old SL. If Binance rejects the new SL due to `-4130` (duplicate stop), use a temporary `STOP_MARKET` at a slightly different price as a bridge.

---

### Finding 2: Fire-and-Forget ML Task Accumulation Under Tick Bursts
**Severity:** HIGH  
**Location:** `Engine_1.py` L665-668 (`SnapshotStore.update`)

```python
if price_fresh and self.predictor:
    def _run_ml_predictors(sym, snap_obj, tracker):
        self.predictor.on_tick_update(sym, snap_obj, tracker)
    asyncio.create_task(asyncio.to_thread(_run_ml_predictors, symbol, new_snap, self.trade_tracker))
```

**Impact:** Every price update spawns a new `asyncio.Task` wrapping `asyncio.to_thread()`. At 180 ticks/sec (18 symbols × 10 Hz), this creates 180 tasks/sec. The `_on_tick_locked` method returns immediately for duplicate bars, but the task creation overhead (coroutine allocation, thread pool submission) is non-trivial. Over 72 hours, this generates ~46.6 million tasks. The default `ThreadPoolExecutor` (os.cpu_count() + 4 workers) becomes a bottleneck, and pending tasks accumulate in the asyncio event loop queue, causing jitter in `renderer_loop` and `poll_loop`.

**Mitigation Required:** Throttle ML dispatch to once per candle close, not per tick. Add a per-symbol `_last_ml_dispatch_ts` guard:

```python
now = time.time()
if now - self._last_ml_dispatch_ts.get(symbol, 0) < 5.0:
    return  # Skip if dispatched within last 5 seconds
self._last_ml_dispatch_ts[symbol] = now
```

---

### Finding 3: Trade Tracker Lock Contention Blocks Multi-Symbol Updates
**Severity:** HIGH  
**Location:** `Engine_1.py` L655-662 (`SnapshotStore.update`)

```python
if self.trade_tracker and price_updated:
    self.trade_tracker.check_exits(symbol, new_snap.price, atr_dict)
    self.trade_tracker.update_live_pnl(symbol, new_snap.price, self)
```

Both `check_exits()` and `update_live_pnl()` acquire `self.trade_tracker.lock` (RLock). `update_live_pnl()` can trigger `emergency_halt` which iterates ALL active trades and closes them — holding the lock for the entire iteration. This blocks ALL other symbols' `SnapshotStore.update()` calls that are waiting to acquire their per-symbol `asyncio.Lock`, because the trade tracker operations happen INSIDE the `async with self._locks[symbol]` block.

**Impact:** During an emergency halt, all 18 symbols' updates are serialized behind the halt operation. If closing 5 trades takes 200ms, all other symbol updates are delayed by 200ms.

**Mitigation Required:** Move trade tracker operations outside the per-symbol asyncio lock. Snapshot the price, release the lock, then call trade tracker methods.

---

### Finding 4: coinglass_scraper.py `reconnect()` Bypass Guard Prevents Recovery
**Severity:** HIGH  
**Location:** `engine_components/coinglass_scraper.py` L249-252

```python
async def reconnect(self, focus_lock: asyncio.Lock) -> None:
    if self.indicators_injected:
        log.info(f"[{self.tab_id}] Indicators are already injected — bypassing tab reconnect...")
        return
```

**Impact:** If the watchdog detects a hung tab and calls `reconnect()`, but `indicators_injected` is still `True` (because the page reload in `poll_loop` hasn't reset it yet due to a race), the reconnect is silently skipped. The tab remains broken with no recovery path. The `poll_loop` resets `self.indicators_injected = False` AFTER `page.reload()`, but if the reload itself fails or stalls, the flag remains `True`.

**Mitigation Required:** Remove the `indicators_injected` bypass from `reconnect()`. The flag should only gate the initial `inject_and_configure_all()` call, not recovery paths.

---

### Finding 5: `tab_switcher` References Non-Existent `active_tab.name` Attribute
**Severity:** MEDIUM  
**Location:** `Engine_1.py` L2473-2478 (in `main()`)

```python
except asyncio.TimeoutError:
    print(f"[Switcher] Warning: focus_lock timeout. Bypassing lock to force {active_tab.name} to front.")
```

**Impact:** `CoinglassTab` has no `.name` attribute — only `.tab_id`. This causes an `AttributeError` crash in the exception handler, which kills the `tab_switcher` coroutine silently. After this crash, tabs are never switched again, leading to OS/browser background tab throttling on the inactive tab.

**Fix:** Replace `active_tab.name` with `active_tab.tab_id`.

---

### Finding 6: `get_process_memory_usage()` Windows-Only, Returns 0 on Linux
**Severity:** MEDIUM  
**Location:** `Engine_1.py` L62-83

```python
def get_process_memory_usage() -> int:
    try:
        psapi = ctypes.windll.psapi  # Windows-only
        ...
    except Exception:
        pass
    return 0
```

**Impact:** On Linux deployments, memory monitoring is completely blind. The watchdog's 3.5 GB alert never fires. Memory leaks grow undetected until OOM-kill.

**Fix:** Add `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` fallback for Linux.

---

### Finding 7: `FootprintCandle.volume_profile` Unbounded Within 15m Window
**Severity:** LOW  
**Location:** `Engine_1.py` L524-540

```python
self.volume_profile: Dict[float, float] = collections.defaultdict(float)
```

**Impact:** Each unique price bucket adds a key. For BTC with tick_size=10.0 and a 5% price swing in 15 minutes (~$5000 range), that's ~500 keys. Not a real leak, but during extreme volatility, could grow to thousands of entries per symbol. Cleared on new candle open, so bounded by candle duration.

---

### Finding 8: `Engine1TradeTracker.history` Unbounded Growth
**Severity:** LOW  
**Location:** `Engine_1.py` L280-310

**Impact:** `self.history` grows with every closed trade. Over 72 hours at ~50 trades/day, that's ~150 trade dicts. Over a year, ~18,000. Each dict is ~500 bytes. Total: ~9 MB. Not a practical leak, but `save_history()` serializes the entire list to JSON on every close, which becomes slow.

**Mitigation:** Archive trades older than 30 days to a separate file. Keep only recent trades in the active JSON.

---

## STEP-BY-STEP SIMULATION TRACES

### SCENARIO A: Concurrent Focus Contention & Lock Starvation

**Setup:** `tab_switcher`, `watchdog`, and `poll_loop` all compete for resources.

**Trace:**

| Time (ms) | Component | Action | Lock State |
|-----------|-----------|--------|------------|
| T+0 | `tab_switcher` | Attempts `async with focus_lock` | `focus_lock` FREE → ACQUIRED |
| T+0 | `watchdog` | Detects Tab1 heartbeat > 90s | — |
| T+0 | `poll_loop` (Tab1) | Calls `frame.evaluate()` | Does NOT use `focus_lock` |
| T+100 | `tab_switcher` | Calls `active_tab.page.bring_to_front()` | `focus_lock` HELD |
| T+200 | `watchdog` | Calls `tab1.reconnect(focus_lock)` | — |
| T+200 | `reconnect()` | Calls `self.page.close()` | — |
| T+200 | `poll_loop` (Tab1) | `frame.evaluate()` throws "Target closed" | — |
| T+200 | `poll_loop` (Tab1) | `self.poll_failures += 1` | — |
| T+300 | `tab_switcher` | Releases `focus_lock` | `focus_lock` FREE |
| T+300 | `reconnect()` | `inject_and_configure_all()` acquires `focus_lock` | `focus_lock` ACQUIRED |
| T+300 | `reconnect()` | `self.start()` creates new page | — |
| T+15300 | `reconnect()` | 15s layout wait completes | — |
| T+15300 | `reconnect()` | JS injection begins (9 symbols × ~2s each) | — |
| T+33300 | `reconnect()` | 15s study wait completes | — |
| T+33300 | `reconnect()` | Releases `focus_lock` | `focus_lock` FREE |
| T+33300 | `watchdog` | Creates new `poll_loop` task | — |
| T+33800 | `poll_loop` (Tab1) | First successful extraction | Heartbeat reset |

**Deadlock Analysis:** NO deadlock. `asyncio.Lock()` is cooperative (not OS-level). The 3.0s timeout in `tab_switcher` ensures it never blocks indefinitely. `poll_loop` does not acquire `focus_lock` at all, so it cannot deadlock with `reconnect()`.

**However:** There IS a data corruption risk. When `reconnect()` calls `self.page.close()`, the running `poll_loop` is still referencing `self.page`. The `watchdog` cancels the old `poll_loop` task BEFORE calling `reconnect()`, but `asyncio.Task.cancel()` only sets a `CancelledError` at the next `await` point. If `poll_loop` is in the middle of `asyncio.gather(*[_fetch_frame(i) for i in range(1, 10)])`, the cancellation propagates to all 9 sub-tasks, but some may have already passed their last `await` and are executing synchronously. These sub-tasks may access `self.page` after it's been closed.

**Verdict:** No deadlock. Race condition exists but is benign (errors are caught by try/except). Recovery time: ~33 seconds.

---

### SCENARIO B: Rapid Market Volatility & Binance Order Collision

**Setup:** 5% BTC flash crash in 3 seconds. S1 triggers LONG entry, S4 triggers SHORT exit on BTC.

**Trace:**

| Time (ms) | Component | Action |
|-----------|-----------|--------|
| T+0 | Binance WS | BTC price drops from $100,000 to $95,000 |
| T+50 | `store.update("BTCUSDT", price=95000)` | Acquires `asyncio.Lock` for BTCUSDT |
| T+50 | `check_exits("BTCUSDT", 95000, atr_dict)` | Acquires `trade_tracker.lock` (RLock) |
| T+50 | S4 trade: `current_price <= sl` → `should_close = True` | Reason: "SL" |
| T+50 | `close_position` dispatched to `broker_executor` | MT5 close submitted (1 worker thread) |
| T+51 | `trade_tracker.lock` released | — |
| T+100 | ML prediction fires (via `asyncio.to_thread`) | — |
| T+100 | `_on_tick_locked` evaluates S1 signal | `mc > 0, p8 < -0.12` → direction = 1 (LONG) |
| T+100 | `trigger_entry("BTCUSDT", "S1_Liquidation", 1, 95000, ...)` | Acquires `trade_tracker.lock` |
| T+100 | Checks: no active S1 trade on BTCUSDT | PASS |
| T+100 | `mt5_broker.execute_trade(...)` | MT5 market BUY at $95,000 |
| T+200 | MT5 fill confirmed | Trade recorded in `active_trades` |
| T+200 | `trade_tracker.lock` released | — |

**Simultaneous `modify_sltp` during trailing stop:**

| Time (ms) | Component | Action |
|-----------|-----------|--------|
| T+0 | `check_exits` | Trailing stop: `new_sl > sl` → calls `_broker_submit(modify_sltp, ...)` |
| T+0 | `broker_executor` | Queued (1 worker thread, serialized) |
| T+100 | `modify_sltp` begins | Cancels ALL algo orders for symbol |
| T+100 | **NAKED WINDOW STARTS** | No SL on exchange |
| T+2500 | New SL placed via `/fapi/v1/algoOrder` | **NAKED WINDOW ENDS** |
| T+2500 | New TP placed | — |

**Binance `-4130` ("An open stop order exists"):**
The code cancels ALL algo orders first, then places new ones. If a race causes `-4130`, `_place_algo_conditional` falls back to `/fapi/v1/order` (standard order endpoint). If that also fails, `modify_sltp` calls `close_position()` — emergency close.

**Binance `-4138` ("Order price out of bounds"):**
This occurs when the new SL price is outside the exchange's `PRICE_FILTER`. The `_format_price` method rounds to `tick_size`, but if the price has moved >5% and the SL is now far from current price, the exchange may reject it. The code handles this by falling back to `close_position()`.

**API Timeout (4.0s):**
`_request()` has `timeout=15` in `urllib.request.urlopen`. If the request hangs for 4 seconds, it's still within the 15s timeout. The `_backoff_sleep` uses `time.sleep(0.01)` loops, which block the thread but not the event loop (since it runs in `broker_executor`).

**Verdict:** The S1/S4 collision is handled correctly — different strategies can coexist on the same symbol. The trailing stop naked window (2.5s) is the primary risk. Emergency close is the fallback.

---

### SCENARIO C: 72-Hour Memory Stability

**Collection Analysis:**

| Collection | Type | Bounded? | Max Size (72h) | Leak Risk |
|-----------|------|----------|-----------------|-----------|
| `_response_tasks` | `set[Task]` | YES (auto-discard on done) | ~100 active | NONE |
| `SnapshotStore._data` | `Dict[str, AssetSnapshot]` | YES (18 symbols) | 18 entries | NONE |
| `SnapshotStore._locks` | `Dict[str, Lock]` | YES (18 symbols) | 18 entries | NONE |
| `FootprintCandle.volume_profile` | `defaultdict` | YES (cleared per candle) | ~500 keys/candle | NONE |
| `candles_history` | `deque(maxlen=1200)` | YES | 1200 × 18 = 21,600 | NONE |
| `trade_tracker.history` | `list` | **NO** | ~150 trades | LOW |
| `reentry_cooldown_until` | `dict` | YES (bounded keyspace) | 108 entries | NONE |
| `_cached_signals` | `dict` | YES (18 symbols) | 18 entries | NONE |
| Playwright listeners | callbacks | YES (per page lifecycle) | 3 per page | NONE |
| ML fire-and-forget tasks | `asyncio.Task` | **NO** | ~46.6M created | **HIGH** |

**ML Task Accumulation Deep Dive:**

Each `asyncio.create_task(asyncio.to_thread(...))` creates:
- 1 coroutine object (~200 bytes)
- 1 `asyncio.Task` object (~500 bytes)
- 1 thread pool submission (~100 bytes)

At 180/sec × 72h × 3600s = 46,656,000 tasks. Most complete in <1ms (early return from `_on_tick_locked`), but the GC overhead of collecting 46M short-lived objects causes periodic GC pauses. Python's generational GC runs every 700 allocations in gen0, so this triggers ~66,000 GC cycles over 72 hours.

**Win32 `get_process_memory_usage()`:** Returns `PrivateUsage` (committed memory). Does NOT reflect Chrome IPC shared memory or Playwright's CDP buffer allocations. Chrome's memory is tracked separately by the OS.

**Verdict:** The ML task firehose is the primary memory concern. Not a traditional leak, but a GC pressure issue. The trade history list is a slow leak but manageable over 72 hours.

---

### SCENARIO D: Event Loop Responsiveness Under Tick Bursts

**Setup:** 18 symbols × 10 ticks/sec = 180 WebSocket messages/sec.

**Trace per tick:**

| Step | Operation | Time (μs) | Blocks Event Loop? |
|------|-----------|-----------|-------------------|
| 1 | `json.loads(raw)` | ~50 | YES (CPU) |
| 2 | `store.update()` → acquire `asyncio.Lock` | ~5 | YES (if contended) |
| 3 | `dataclasses.replace()` | ~10 | YES (CPU) |
| 4 | `trade_tracker.check_exits()` → acquire RLock | ~100-5000 | YES (if emergency halt) |
| 5 | `trade_tracker.update_live_pnl()` → acquire RLock | ~50-200 | YES |
| 6 | `asyncio.create_task(asyncio.to_thread(...))` | ~20 | YES |
| 7 | Release `asyncio.Lock` | ~2 | YES |

**Worst case per tick:** ~5,400 μs (5.4 ms) if `check_exits` triggers trailing stop modification.

**At 180 ticks/sec:** 180 × 5.4ms = 972ms/sec = **97.2% event loop utilization**. This leaves only 28ms/sec for `renderer_loop` (500ms interval), `poll_loop` (500ms interval), and `event_loop_monitor` (100ms interval).

**Impact on `renderer_loop`:** The 2 Hz refresh (500ms interval) requires ~10ms to render the Rich table. With 97% loop utilization, the `await asyncio.sleep(0.5)` may be delayed by up to 500ms, causing visible terminal stutter.

**Impact on `poll_loop`:** The 500ms poll interval may stretch to 1-2 seconds, causing data staleness. The watchdog's 90s heartbeat threshold is generous enough to avoid false positives.

**Impact on `event_loop_monitor`:** The 100ms `asyncio.sleep(0.1)` will measure the actual delay. If the loop is blocked for >500ms (the threshold), it fires an alert. Under tick bursts, this alert WILL fire frequently.

**ML Pool Saturation:** The default `ThreadPoolExecutor` has `os.cpu_count() + 4` workers (typically 12 on an 8-core machine). Each `_run_ml_predictors` call acquires `self._lock` (RLock) and returns immediately for duplicate bars. But the thread pool submission itself is serialized. At 180 submissions/sec with 12 workers, each worker processes 15 tasks/sec. If each task takes <1ms (early return), the pool handles it. If a task triggers actual ML inference (~50ms), the queue depth grows to ~9 pending tasks per worker.

**Verdict:** The event loop IS saturated under tick bursts. The `renderer_loop` and `poll_loop` experience jitter. The `event_loop_monitor` correctly detects this. The ML pool is NOT saturated due to the early-return guard, but the task creation overhead is significant.

---

### SCENARIO E: Scraper Deadlock & Anti-Bot Challenge Resilience

**Setup:** CoinGlass serves a Cloudflare challenge or mutates iframe DOM.

**Trace — Cloudflare Challenge:**

| Time (s) | Component | Action |
|----------|-----------|--------|
| T+0 | `poll_loop` | `iframe.element_handle(timeout=3000)` → returns handle |
| T+0 | `poll_loop` | `frame.evaluate(SINGLE_FRAME_EXTRACTION_JS)` → returns `{success: true, data: {}}` (empty data because Cloudflare overlay blocks DOM) |
| T+0.5 | `poll_loop` | `has_success = False` (no valid data extracted) |
| T+0.5 | `poll_loop` | `self.poll_failures += 1` |
| ... | ... | Repeats every 0.5s |
| T+2.5 | `poll_loop` | `poll_failures > 5` → triggers `page.reload()` |
| T+5 | `page.reload()` | Cloudflare challenge still present |
| T+5 | `poll_loop` | `poll_failures = 0` (reset after reload) |
| T+7.5 | `poll_loop` | `poll_failures > 5` again → another reload |
| ... | ... | Infinite reload loop |
| T+90 | `watchdog` | Heartbeat > 90s → calls `reconnect()` |
| T+90 | `reconnect()` | `page.close()` + `start()` (new page) |
| T+105 | `start()` | `page.goto(URL)` → Cloudflare challenge again |
| T+135 | `inject_and_configure_all()` | Fails (no chart containers visible) |
| T+135 | `reconnect()` | Reports "Tab successfully restarted" (misleading) |
| T+225 | `watchdog` | Heartbeat > 90s again → another `reconnect()` |

**Maximum Recovery Time:** If Cloudflare challenge resolves itself (typically 5-30 seconds), recovery is ~33 seconds (reconnect time). If Cloudflare persists, the system enters an infinite reconnect loop with no data flow. There is no circuit breaker to halt after N failed reconnects.

**Trace — iframe DOM Mutation:**

| Time (s) | Component | Action |
|----------|-----------|--------|
| T+0 | `poll_loop` | `iframe.element_handle()` → returns handle |
| T+0 | `frame.evaluate()` | JS executes but selectors don't match → `{success: true, data: {close: 0}}` |
| T+0 | `store.update()` | `price=0.0` → rejected by `if k == "price" and fv <= 0.0: continue` |
| T+0.5 | `poll_loop` | `has_success = False` |
| ... | ... | `poll_failures` increments |
| T+2.5 | `poll_loop` | `poll_failures > 5` → `page.reload()` |
| T+5 | `page.reload()` | DOM re-renders with correct structure |
| T+5 | `poll_loop` | Extraction succeeds → heartbeat reset |

**Recovery Time:** ~5 seconds for DOM mutation. The `page.reload()` in `poll_loop` is the primary self-healing mechanism.

**Trace — "Execution context was destroyed":**

| Time (s) | Component | Action |
|----------|-----------|--------|
| T+0 | `poll_loop` | `frame.evaluate()` throws `Execution context was destroyed` |
| T+0 | `_fetch_frame` | Catches exception, returns `False` |
| T+0.5 | `poll_loop` | All 9 frames fail → `has_success = False` |
| T+0.5 | `poll_loop` | `poll_failures += 1` |
| T+2.5 | `poll_loop` | `poll_failures > 5` → `page.reload()` |
| T+5 | `page.reload()` | New execution contexts created |
| T+5 | `poll_loop` | Extraction succeeds |

**Verdict:** The self-healing `page.reload()` at `poll_failures > 5` handles transient DOM issues. Cloudflare challenges cause infinite reload loops with no circuit breaker. Maximum recovery time for non-Cloudflare issues: ~5 seconds. For Cloudflare: unbounded.

---

## ARCHITECTURAL HARDENING RECOMMENDATIONS

### R1: Implement Place-Then-Cancel SL/TP Modification (CRITICAL)

**Current:** Cancel old → Place new (naked window: 1-5s)  
**Proposed:** Place new at slightly different price → Confirm → Cancel old

```python
def modify_sltp(self, symbol, position_ticket, sl, tp):
    # 1. Place new SL at sl + 0.01% (bridge price)
    bridge_sl = sl * 1.0001 if pos_amt > 0 else sl * 0.9999
    new_sl = self._place_algo_conditional(symbol, opposite_side, "STOP_MARKET", bridge_sl, "BRIDGE_SL")
    
    # 2. If bridge SL placed, cancel old SL
    if new_sl:
        self._cancel_old_algo_orders(symbol, exclude_algo_id=new_sl["algoId"])
        
        # 3. Modify bridge SL to exact target price
        self._request("PUT", "/fapi/v1/algoOrder", params={
            "symbol": symbol, "algoId": new_sl["algoId"], "triggerPrice": str(sl)
        })
```

### R2: Throttle ML Task Dispatch to Candle Boundaries (HIGH)

Replace fire-and-forget per-tick dispatch with a candle-close-only dispatch:

```python
# In SnapshotStore.update(), replace the ML dispatch block:
if price_fresh and self.predictor:
    open_time = int(time.time() // 900) * 900
    last_dispatch = self._last_ml_dispatch.get(symbol, 0)
    if open_time > last_dispatch:
        self._last_ml_dispatch[symbol] = open_time
        asyncio.create_task(asyncio.to_thread(_run_ml_predictors, symbol, new_snap, self.trade_tracker))
```

### R3: Move Trade Tracker Operations Outside Asyncio Lock (HIGH)

```python
# In SnapshotStore.update():
async with self._locks[symbol]:
    # ... update snapshot ...
    self._data[symbol] = new_snap

# OUTSIDE the lock:
if price_fresh and self.trade_tracker:
    self.trade_tracker.check_exits(symbol, new_snap.price, atr_dict)
    self.trade_tracker.update_live_pnl(symbol, new_snap.price, self)
```

### R4: Add Cloudflare Circuit Breaker (MEDIUM)

```python
# In watchdog, after 3 consecutive failed reconnects:
if reconnect_failures >= 3:
    log.critical(f"[Watchdog] Cloudflare/anti-bot detected. Halting tab {c.tab_id} for 5 minutes.")
    await asyncio.sleep(300)
    reconnect_failures = 0
```

### R5: Fix `tab_switcher` AttributeError (TRIVIAL)

Replace `active_tab.name` with `active_tab.tab_id` in both the `TimeoutError` handler and the general exception handler.

### R6: Add Linux Memory Monitoring (MEDIUM)

```python
def get_process_memory_usage() -> int:
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # KB to bytes
    except ImportError:
        pass
    # ... existing Windows code ...
```

### R7: Archive Old Trade History (LOW)

```python
def save_history(self):
    with self.lock:
        recent = [t for t in self.history if t.get('entry_timestamp', 0) > time.time() - 30*86400]
        archived = [t for t in self.history if t.get('entry_timestamp', 0) <= time.time() - 30*86400]
        # Write recent to active file, archived to archive file
```

### R8: Add WebSocket Message Rate Limiter (LOW)

The Binance WS feed already throttles to 150ms per symbol (`last_emit_ns`), which is correct. But the 150ms throttle means price updates lag by up to 150ms during fast markets. Consider reducing to 50ms for symbols with active trades.

---

## SEVERITY SUMMARY

| # | Finding | Severity | Exploitable? | Fix Complexity |
|---|---------|----------|--------------|----------------|
| 1 | Naked SL/TP window on Binance | **CRITICAL** | Yes (flash crash) | Medium |
| 2 | ML task firehose (46M tasks/72h) | **HIGH** | No (perf degradation) | Low |
| 3 | Trade tracker lock blocks all symbols | **HIGH** | No (latency spike) | Low |
| 4 | `reconnect()` bypass guard | **HIGH** | Yes (tab stays broken) | Trivial |
| 5 | `active_tab.name` AttributeError | **MEDIUM** | No (silent crash) | Trivial |
| 6 | Windows-only memory monitoring | **MEDIUM** | No (blind on Linux) | Low |
| 7 | FootprintCandle unbounded dict | **LOW** | No (self-clearing) | None needed |
| 8 | Trade history unbounded growth | **LOW** | No (slow I/O) | Low |

---

*Audit conducted by static analysis of source code at commit `53484ee`. No runtime execution was performed. All findings are based on code-level trace analysis.*
