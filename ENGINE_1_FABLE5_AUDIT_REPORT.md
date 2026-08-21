# Engine_1 Pipeline Audit Report

**Target:** `Engine_1.py` (4,738 lines), branch `arena/019fec7a-coinglass-trading`
**Scope:** Concurrency & locking, error handling & silent failures, data integrity & state machine correctness, resource leaks.
**Method:** Full structural mapping of all classes (`SnapshotStore`, `LiveTradeTracker`, `CoinglassNormalizer`, `BinanceTradePriceWebSocketFeed`, `BinanceFootprintFeed`, `CoinglassTab`, `DualTee` in `Engine_1_arena_PR/Engine_1.py`), plus pattern scans across the file.

---

## Architecture Map (summary)

```
Playwright (CoinglassTab x2) ──┐
Binance WS (aggTrade/forceOrder) ──┤→ SnapshotStore.update()  [asyncio.Lock per symbol + threading.RLock global]
Binance REST (klines/OI feeds) ──┘        │
                                          ├→ CoinglassNormalizer (CVD/funding normalization, disk persistence)
                                          ├→ LiveTradeTracker.check_exits / update_live_pnl  [threading.RLock]
                                          │        └→ BinanceBrokerAdapter → ThreadPoolExecutor("BinanceBroker"/"BinanceEmergency")
                                          └→ ML dispatch → ML_POOL (8 threads) → strategy_armed writeback
main(): 10 asyncio tasks + retrain daemon thread + signal-driven shutdown
```

---

# CRITICAL (P0) — Event-loop stalls & fund-safety

## P0-1. Event loop blocked up to 10s × N trades during emergency halt
- **Location:** `LiveTradeTracker.update_live_pnl`, lines 903–921.
- **Root cause:** `close_futures[tid].result(timeout=10.0)` is a **blocking** `concurrent.futures` wait. `update_live_pnl` is invoked synchronously from the async path `SnapshotStore.update()` (line 1596) on every price tick. During an emergency halt with multiple open trades, the entire asyncio event loop (all WS feeds, scrapers, watchdogs, renderer) freezes for up to 10 seconds **per trade** — exactly when the engine most needs live prices to close positions.
- **Remediation:** Never block the event loop on futures. Dispatch closes and let the existing `reconcile_with_broker` / done-callbacks confirm them; or make the halt path async (`await asyncio.wrap_future(fut)`), or run the whole halt handler in a dedicated thread.

## P0-2. Synchronous broker network call held under the global tracker lock
- **Location:** `LiveTradeTracker.trigger_entry`, line 817 (`self.broker.execute_trade(...)` inside `with self.lock:` opened at 664).
- **Root cause:** `execute_trade` is a blocking HTTP round trip to Binance (order placement + SL attach). While it runs, `self.lock` (RLock) is held. `check_exits` and `update_live_pnl` — called from the **asyncio event loop** on every tick — block on the same lock. One slow order (network jitter, exchange latency) freezes tick processing, exit checks, and trailing stops for **all** symbols.
- **Remediation:** Reserve the trade slot under the lock (insert a `PENDING_SUBMIT` record), release the lock, execute the broker call outside it (ideally via `broker_executor`), then re-acquire to finalize/rollback.

## P0-3. `reconcile_with_broker` holds the tracker lock across multiple network calls
- **Location:** Lines 1176–1254. `list_engine_positions()`, `is_order_pending()`, `has_position()`, `get_last_fill()`, `get_all_positions()` all run inside `with self.lock:`.
- **Root cause:** Even though it is dispatched via `asyncio.to_thread` (line 4578), the RLock is shared with the event loop's synchronous `check_exits`/`update_live_pnl` calls. A reconcile pass with several REST calls (each potentially seconds under degraded network) starves tick processing for its full duration.
- **Remediation:** Snapshot `active_trades` under the lock, perform all network I/O lock-free, then re-acquire the lock to apply a diff (re-validating each trade still exists).

## P0-4. SL heartbeat is dead code — exchange stops are never re-pushed
- **Location:** `check_exits`, lines 977–984.
- **Root cause:** `if now - getattr(self, 'last_sl_heartbeat', now) > 60:` — `last_sl_heartbeat` is only ever assigned **inside** this branch, and the `getattr` default is `now`, so the condition evaluates `0 > 60` on every call forever. The "periodically push current trailing SL to exchange" safety mechanism **never executes**.
- **Remediation:** Initialize `self.last_sl_heartbeat = time.time()` in `__init__` (or use default `0.0`).

## P0-5. Funding-rate normalization contradicts its own contract (100× error for the common case)
- **Location:** `CoinglassNormalizer.normalize_funding`, lines 1377–1393.
- **Root cause:** The docstring states Coinglass DOM values are **always** percentages ("0.01 = 0.01%"), but division by 100 only occurs when `abs(raw) >= 0.05`. A typical DOM reading of `0.01` (meaning 0.01%) passes through as decimal `0.01` = **1%** — a 100× inflation of funding for the majority of readings, directly feeding strategy features and any funding-sensitive signal. Only extreme values (≥5% displayed) are correctly divided.
- **Remediation:** Divide unconditionally for `source == "coinglass_dom"`, and validate the resulting decimal fraction against a plausibility bound (e.g. `abs(f) <= 0.03`). If the DOM format is actually ambiguous, fix the docstring and add a calibration check against the Binance REST funding value already fetched at line ~3221.

## P0-6. `save_history()` swallows all failures — trade ledger loss is silent
- **Location:** Lines 606–652, `except Exception: pass` at 651.
- **Root cause:** The single persistence path for the live trade ledger (P&L, active trades, cooldowns, daily baseline) silently discards disk-full, permission, and serialization errors. On restart the engine would resurrect stale trades or lose closed ones with no operator signal.
- **Remediation:** Log the exception with `log_live_event(..., "FATAL")`, increment a `pipeline_health["ledger_write_failures"]` counter surfaced on the dashboard, and escalate to emergency halt after N consecutive failures.

---

# HIGH (P1) — Concurrency & state-machine defects

## P1-1. Mixed `asyncio.Lock` + `threading.RLock` with sync-lock-in-async antipattern
- **Location:** `SnapshotStore.update`, lines 1468–1469 (`async with self._locks[symbol]: with self._global_lock:`); ML worker writebacks at 1630–1638 acquire `_global_lock` from `ML_POOL` threads.
- **Root cause:** The event loop acquires a `threading.RLock` while ML threads hold it. Contention is currently short, but any slow path inside a `_global_lock` holder (e.g. a future `dataclasses.replace` on a bigger snapshot, or GC pause) blocks the event loop directly. There is also no defined lock ordering between `_locks[symbol]`, `_global_lock`, and `LiveTradeTracker.lock` (acquired at 1595–1596 from the same call stack) — the deadlock-free property is accidental, not designed.
- **Remediation:** Make `SnapshotStore` single-writer (event loop only): ML threads should post `strategy_armed` results to an `asyncio.Queue` / `loop.call_soon_threadsafe` instead of mutating `_data` directly. Then `_global_lock` can be deleted. Document lock hierarchy: `store locks → tracker.lock`, never the reverse.

## P1-2. Lazy, racy initialization of `_ml_pending` / `_ml_lock`
- **Location:** Lines 1619–1622.
- **Root cause:** `if not getattr(self, '_ml_pending', None): self._ml_pending = set()` runs in the update hot path. Concurrent updates for two symbols interleaving at this check can each create a fresh set/lock, dropping the other's pending markers (double ML dispatch). Also `not getattr(...)` re-creates the set whenever it is *empty* — harmless for `set()` but re-creates `_ml_lock` never (truthy) — inconsistent semantics.
- **Remediation:** Initialize both in `__init__` unconditionally.

## P1-3. Untracked fire-and-forget asyncio tasks (GC + shutdown hazard)
- **Location:** Line 2519 (`page.on("response", lambda res: asyncio.create_task(_on_response_safe(res)))`), line 2532, line 1646 (`asyncio.ensure_future(_watch_ml(...))`).
- **Root cause:** Task references are not retained; CPython may garbage-collect a running task mid-flight, and none of these are cancelled or awaited on shutdown. Every Coinglass network response spawns a task with no concurrency bound — a burst of responses floods the loop.
- **Remediation:** Keep a `set` of tasks with `task.add_done_callback(tasks.discard)`; bound response handling with a semaphore; cancel the set in the shutdown `finally` block.

## P1-4. Executors and daemon thread never shut down
- **Location:** `ML_POOL`/`RENDER_POOL` (lines 75–76), `broker_executor`/`emergency_executor` (497–498), `retrain_thread` daemon (4363); shutdown `finally` at 4709–4719 only cancels asyncio tasks and closes browser contexts.
- **Root cause:** In-flight broker submissions (order closes, SL modifies!) can be killed mid-request when the process exits because nothing calls `executor.shutdown(wait=True)`. The 2-hour retraining subprocess (line 4345) is abandoned as a daemon thread — the child `subprocess.run` may survive or be killed mid-write of model files.
- **Remediation:** In the shutdown path: `broker_executor.shutdown(wait=True)` and `emergency_executor.shutdown(wait=True)` **before** process exit (these carry money-moving calls); `ML_POOL.shutdown(cancel_futures=True)`; make the retrain loop observe the `stop` event and terminate its subprocess handle explicitly.

## P1-5. Shutdown does not persist the trade ledger
- **Location:** `sig_handler`, lines 4686–4696.
- **Root cause:** The signal handler saves `store.normalizer.save_state()` but never calls `trade_tracker.save_history()`. Any trailing-SL updates, cooldowns, or capital changes since the last event-driven save are lost on SIGINT/SIGTERM.
- **Remediation:** Add `trade_tracker.save_history()` (and flush `DualTee`) to the shutdown finally block.

## P1-6. Broker-close path skips `full_trade_callbacks`; cooldown armed before close confirmed
- **Location:** `check_exits`: broker path 1085–1121 vs. dry-run path 1122–1137; cooldown at 1139–1142.
- **Root cause:** (a) When a close is dispatched to the broker, the done-callback (1088–1117) appends history and adjusts capital but **never invokes `full_trade_callbacks`**, so downstream consumers (strategy feedback, journaling) see dry-run closes but not live closes. (b) The re-entry cooldown is set at dispatch time even if the close later fails and the trade is re-armed (line 1111) — the engine then refuses re-entry on a symbol it still holds is fine, but if the trade eventually SLs again the cooldown clock started too early. (c) `any_closed` is never set on the broker path, so `save_history()` at 1150 is skipped for live closes (only saved inside the callback — inconsistent but survivable).
- **Remediation:** Move callbacks + cooldown arming into the close-confirmed callback; unify the two close paths into one `_finalize_close(trade, exit_price, reason)` helper.

## P1-7. Unbounded WS reconnection with no circuit breaker or terminal state
- **Location:** `BinanceTradePriceWebSocketFeed.run`, lines 1773–1874.
- **Root cause:** Backoff caps at ~5s and retries forever; `pipeline_health["binance_ws_status"]` shows RECONNECTING but nothing escalates after e.g. 100 consecutive failures, and `skip_watchdog = True` (line 1737) exempts it from the watchdog. A permanently ISP-blocked WS silently degrades liquidation data (`liq_long/liq_short`) to frozen zeros while strategies keep trading on them.
- **Remediation:** After N consecutive failures, mark the feed DEGRADED in `pipeline_health`, zero/expire the liquidation fields via the freshness contracts, and surface an operator alert.

---

# MEDIUM (P2) — Data integrity

## P2-1. CVD accumulator seeded with viewport-relative raw value; reset heuristic can swallow real flow
- **Location:** `CoinglassNormalizer.normalize_cvd`, lines 1349–1375.
- **Root cause:** On first observation, `accumulated_dict[symbol] = raw_cvd` — the "absolute" series is initialized with a viewport-relative number, so the series origin is arbitrary per session (mitigated only by the 4h state file). Worse, the reset detector (`abs(delta) > abs(accumulated) * 0.5 and abs(delta) > min_thresh`) discards the delta entirely (line 1370 returns `accumulated` without adding), so a genuine whale-driven CVD move larger than 50% of accumulated is **misclassified as a viewport reset and dropped** — precisely the events strategies like `S2_CVD_Momentum` care about.
- **Remediation:** Seed `accumulated = 0.0` at baseline; distinguish resets from real moves using a secondary signal (price/volume tick from Binance WS in the same window, or the sign/shape of the raw series), and log every reset decision for calibration. Add a `threading.Lock` if this is ever called outside `store.update`'s serialized path.

## P2-2. Float equality on monetary fields
- **Location:** Lines 1543–1558 (`d_bid == 0.0`, `abs(c_bid - d_bid) < 1e-4` on dollar notionals), 3060–3069, 3143–3173.
- **Root cause:** Bid/ask notional dedup compares dollar values with an absolute epsilon of `1e-4` — meaningless at BTC notional scale (`1e-4` of $500k) and simultaneously too coarse for micro-priced assets; `== 0.0` sentinels conflate "no data" with "true zero" (a legitimately zero liq/funding reading is treated as missing at 3069/3143).
- **Remediation:** Use relative tolerance (`math.isclose(rel_tol=1e-6)`) for duplication detection; replace `0.0`-as-missing with `None`/explicit staleness timestamps (the `_field_last_updated` machinery already exists — use it).

## P2-3. Emergency-halt exit prices bypass the store API and can be stale entry prices
- **Location:** `update_live_pnl` lines 926–930 (`store._data.get(trade_sym)` direct private access; falls back to `trade['entry_price']`).
- **Root cause:** Reading `store._data` outside the store's locking discipline is fragile against refactors; falling back to entry price records a fictitious break-even exit in the ledger while the broker fill happens at the real market price — ledger and exchange P&L diverge exactly during halts.
- **Remediation:** Use `store.snapshot()`; when no price is available, mark the trade `exit_price_estimated=True` and let `reconcile_with_broker` overwrite with the actual fill.

## P2-4. Duplicate/overwriting broker-result assignments
- **Location:** Lines 832–834: `symbol` overwritten with `broker_res.get("symbol")` (may be `None`, corrupting all subsequent symbol-keyed lookups for this trade), and `order_id` assigned twice.
- **Remediation:** `broker_res.get("symbol") or symbol`; delete the duplicate line.

## P2-5. `load_history` capital baseline ignores archived realized P&L
- **Location:** Lines 587, 600–602.
- **Root cause:** `current_capital = initial_capital` (broker balance if connected, else constructor default). In dry-run/testnet-degraded mode where `connect()` fails, restart resets capital to the constructor default and re-loads open trades whose P&L then applies against the wrong baseline. Governance DD limits (lines 675–684) are therefore computed off a potentially wrong equity base.
- **Remediation:** When broker balance is unavailable, replay realized P&L from history to reconstruct capital, and log which baseline source was used.

## P2-6. `finite_float_or_none` shadowed inside the WS hot loop
- **Location:** Lines 1803–1810 redefine the module-level function (line 178) inside the per-message loop, including an `import math` per message.
- **Remediation:** Delete the inner definition; the module-level one already exists.

---

# MEDIUM (P2) — Silent failures (systemic)

~110 broad `except` handlers exist; the highest-impact silent ones beyond P0-6:

| Location | What is swallowed | Risk |
|---|---|---|
| 1864–1865 `except Exception as inner_e: continue` | Every WS message parse/update error, **including `store.update` failures** | Liquidation + price data silently dropped; `inner_e` bound but never logged |
| 4141–4142 `except Exception as audit_err: pass` | Watchdog audit errors (variable bound, never used) | Watchdog blind spots |
| 1097, 1126, 1226 `ruflo_bridge.log_trade_closure` → `pass` | Trade-closure journaling failures | Strategy-feedback data loss |
| 952–953, 967–970 callback errors → `pass` | on_close callback failures | Cooldown/capital listeners silently broken |
| 2163–2264 (CoinglassTab, ~8 instances) `pass` | Browser focus/frame failures | Scraper degrades invisibly until watchdog timeout |
| 1925–1926 fetch errors → `pass` | Per-symbol kline failures (only aggregate warning) | Per-symbol staleness invisible |

- **Remediation:** Adopt a minimum standard: every handler logs `symbol/context + repr(e)` at least once per N occurrences (rate-limited), and increments a per-subsystem `pipeline_health` error counter. No bare `pass` on any path that touches money, the ledger, or the store.

---

# LOW (P3) — Resource management & hygiene

1. **`DualTee` file handle never closed** (`Engine_1_arena_PR/Engine_1.py` 63–102): opened append-mode at import, no `close()`, no rotation — `live_engine_output.txt` grows unboundedly and swallows its own write errors (`except: pass` in `write`). Remediate with `logging.handlers.RotatingFileHandler` and an `atexit` flush/close.
2. **Renderer debug writes via `asyncio.to_thread`** (4078) with per-iteration file open — verify handle closure and add rotation.
3. **`taskkill /F /IM chrome.exe`** (4212–4214) kills **every** Chrome on the machine, not just the engine's profile. Track the launched browser PID and kill by PID.
4. **`subprocess.run` calls** have timeouts (2h retrain, taskkill capture) — acceptable, but retrain results are only `print`ed; failed retrains should flip a health flag.
5. `pipeline_health` dict is mutated lock-free from event loop + ML threads + feed tasks — GIL-safe for scalar writes, but `setdefault("last_change_ns", {})` (1494) from multiple contexts is a latent race; pre-create all keys in `__init__`.
6. Duplicate `import os` (lines 6, 8); dead `closed_trades` list (527); `_translate_to_binance_price` is an identity function kept for interface parity — fine, but document it.
7. `is_field_stale` returns `False` when a field was **never** updated (`last_ts == 0.0`, line 1456) — "never received" is treated as "fresh". Invert: never-updated fields older than one contract interval since boot should be stale.

---

# Prioritized Remediation Order

1. **P0-4** (one-line fix, restores SL heartbeat safety net) and **P0-6** (log ledger failures).
2. **P0-1 / P0-2 / P0-3** — remove all blocking network/futures waits from paths reachable by the event loop; establish the lock hierarchy.
3. **P0-5** — funding normalization calibration against Binance REST ground truth.
4. **P1-4 / P1-5** — ordered shutdown: stop feeds → drain broker executors → save ledger + CVD state → cancel tasks → close browser.
5. **P1-1 / P1-2 / P1-3** — single-writer store, pre-initialized sync primitives, tracked tasks.
6. **P1-6 / P1-7, P2-x** — close-path unification, CVD reset detector, float tolerance and staleness semantics.
7. **P3** sweep — logging standard for all except blocks, DualTee rotation, scoped Chrome kill.

**Overall assessment:** The architecture (per-symbol async locks, freshness contracts, reconciliation loop, dispatch throttles) shows deliberate hardening, but the highest-severity defects are all of one family: **blocking work performed while holding locks shared with the asyncio event loop**, plus two logic bugs (dead SL heartbeat, funding 100× scale) that directly affect fund safety and signal quality.
