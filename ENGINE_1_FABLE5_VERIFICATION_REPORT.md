# Claude Fable 5 — Post-Remediation Verification & Live Deployment Readiness Audit

**Target:** `Engine_1.py` (4,738 lines) + `engine_components/binance_broker.py`
**Branch:** `arena/019fec7a-coinglass-trading`
**Actual HEAD:** `71e28af` — `feat: refactor Engine_1 pipeline for concurrency and error handling improvements`

> **Discrepancy:** The brief claims the latest commit is `c936871` ("chore: Fable 5 phase 1-7 profitability audit fixes"). That SHA does not exist in this branch's history. The verified commit is `71e28af`. All findings below are against the actual working tree.

---

## Vector 1 — Concurrency & Thread-Safety Regression: **FAIL**

### What was genuinely fixed
- `broker_executor` (2 workers) + `emergency_executor` (1 worker) exist (lines 497–498).
- `_broker_submit_checked` (line 538) dispatches SL/TP modifies asynchronously and its done-callback correctly re-acquires `self.lock` before mutating trade state — this pattern is sound because `self.lock` is a `threading.RLock` acquired from the executor thread.
- `check_exits` close path (line 1119) dispatches `close_position` to the executor with a callback that re-arms `closing_dispatched = False` on failure — a correct compare-and-recover state machine.
- Emergency-halt closes are now pre-dispatched in parallel (line 907) before results are collected.

### Regressions / unfixed blockers
1. **`trigger_entry` still executes the live order synchronously under the global lock** (line 817): `self.broker.execute_trade(...)` runs inside `with self.lock:` on the caller's thread — which is the asyncio event-loop thread. Every entry freezes ALL tick processing, exit checks, and WebSocket state updates for the full REST round trip (up to 15s per `urlopen` timeout in `binance_broker._request`, times retries). This was the original P0; the ThreadPool remediation was applied to modifies and closes but **not to entries**.
2. **Emergency halt still blocks the event loop under lock** (line 916): `fut.result(timeout=10.0)` inside `with self.lock` inside `update_live_pnl`. Dispatch is parallel now, but collection is serial on the event-loop thread — with N open trades and a dead broker, the loop freezes up to N×10s during the exact moment (drawdown breach) when responsiveness matters most.
3. **REST call under lock inside a done-callback** (line 1104): `make_close_cb` calls `self.broker.broker.get_account_details()` while holding `self.lock` from a broker thread. Any event-loop code waiting on the lock stalls for that REST round trip.
4. **`reconcile_with_broker` holds the lock across multiple REST calls** (lines 1176–1205): `list_engine_positions`, `is_order_pending`, `has_position`, `get_last_fill` — all network I/O under the global lock.
5. **Mixed lock domains remain**: per-symbol `asyncio.Lock` (line 1400) + global `threading.RLock` (line 1404) guarding overlapping state in `SnapshotStore`.
6. Minor: `_log_done` in `_broker_submit_checked` (line 557) prints "SL modify failed" for ANY dispatched function, mislabeling failed closes.

---

## Vector 2 — Error Recovery & Network Resilience: **WARNING**

### What was genuinely fixed
- `binance_broker._request` handles HTTP 429/418 with `Retry-After`-aware exponential backoff and `max_retries` (broker lines 138–154). **PASS** on rate limits.
- Binance WS feed has bounded-growth reconnect backoff with attempt counter (lines 1870–1873), `ping_interval=10`, `ping_timeout=10`, `open_timeout=3`. **PASS** on WS disconnect handling.
- `UNVERIFIED_OPEN_POSITION` after SL-attach failure keeps the trade, tags `needs_manual_attention`, and dispatches a recovery close (lines 822–830). **PASS** on the naked-position case.
- `execute_trade` exceptions in `trigger_entry` now abort the phantom trade (lines 818–821).

### Unfixed
1. **The "silent exceptions replaced with robust logging" claim is false.** 115 bare `except Exception:` blocks remain. The single worst one survives verbatim: `save_history()` ends in `except Exception: pass` (lines 651–652). **A failed ledger write — the source of truth for capital, active trades, and daily-DD baseline — is still silently discarded.** After a disk-full or permissions event, a restart resurrects stale capital and phantom active trades with zero warning.
2. `ruflo_bridge.log_trade_closure` failures are swallowed silently in three places (lines 952, 1097, 1126).
3. `on_close_callbacks` failures swallowed silently (lines 969, 1147) while `full_trade_callbacks` failures are logged — inconsistent.

---

## Vector 3 — Graceful Shutdown & Resource Cleanup: **FAIL (claim unverifiable)**

1. **`DualTee` does not exist in this file.** `grep -n "DualTee" Engine_1.py` returns nothing. The claimed "`DualTee.close()` implementation" cannot be audited because the class was removed entirely (stdout is only `reconfigure`'d to UTF-8/line-buffering at lines 11–13, 80–81). Either the remediation note is stale or the fix landed in a different file. A copy exists only in `Engine_1_arena_PR/Engine_1.py`, which is not the executing artifact.
2. What IS present and correct: `SIGINT`/`SIGTERM` handlers set the stop event and flag all feeds (lines 4686–4702), `KeyboardInterrupt`/`SystemExit` route to the same handler (line 4707), tasks are cancelled and gathered with `return_exceptions=True`, browser contexts closed (lines 4709–4719), CVD normalizer state saved (line 4696).
3. **`broker_executor` and `emergency_executor` are never `.shutdown()`.** Their non-daemon threads are joined by the interpreter's atexit hook, which blocks final exit until any in-flight 15s-timeout REST call completes, and any queued-but-unstarted broker actions (e.g., a final SL modify) execute after the ledger's last save — or are dropped if the pool is mid-teardown.
4. **No final `trade_tracker.save_history()` on shutdown.** The sig handler saves only the CVD normalizer. If the last state change happened between event-driven saves, it is lost.

---

## Vector 4 — Zero-Divergence Assurance: **FAIL**

Two P0 divergence bugs from the prior audit survived remediation untouched:

1. **The SL heartbeat is still dead code** (line 978):
   ```python
   if now - getattr(self, 'last_sl_heartbeat', now) > 60:
       self.last_sl_heartbeat = now
   ```
   On first call the attribute is missing, `getattr` defaults to `now`, the condition evaluates `0 > 60` → False, and the attribute is **never assigned** (assignment is inside the branch). The condition is therefore false on every call, forever. Exchange-side stops are never re-pushed by the heartbeat; the only exchange-SL syncs are trailing-ratchet modifies. If a modify is dropped (tagged `needs_manual_attention`), the exchange stop diverges from the local stop permanently.

2. **`normalize_funding` still contradicts its own docstring** (lines 1377–1393). The docstring says "Coinglass DOM: always displays as percentage," yet the code divides by 100 only when `|raw| >= 0.05`. A typical DOM reading of `0.01` (meaning 0.01% = 0.0001 decimal) passes through unchanged as `0.01` — **a 100× inflation**. Worse, the mapping is non-monotonic at the 0.05 boundary: a displayed `0.04` normalizes to `0.04` while a displayed `0.06` normalizes to `0.0006` — a HIGHER real funding rate produces a LOWER feature value. Any funding-sensitive model feature diverges live vs. backtest by construction. Static parity checks pass only because both sides of the parity harness consume the same (wrong) normalization.

3. **Emergency-halt exit prices are synthetic** (lines 923–930): last snapshot price or `entry_price` fallback, not actual fills — recorded PnL diverges from broker PnL in exactly the scenarios (halts) where accounting accuracy matters.

4. Comment/code mismatch on trailing activation (lines 1008–1013): comments say "Activate after reaching 2R" while the code activates at `5.0 * entry_atr`. If `run_all_6.py` backtests 2R activation, live trailing behavior diverges on every trade that runs between 2R and 5×ATR.

---

## Edge Case Analysis (Black Swans)

**Black Swan 1 — Exchange outage during a drawdown breach.** Daily DD crosses 10% while Binance REST is returning 5xx/timeouts. `update_live_pnl` holds the global lock and collects `fut.result(timeout=10.0)` per trade on the event-loop thread. With 5 open trades: up to 50s of total engine freeze per tick cycle — no WS processing, no exits on other symbols, no watchdog heartbeats (risking a spurious watchdog restart at the 120s threshold, line 4160). Meanwhile `emergency_executor` has `max_workers=1`, so the "parallel pre-dispatch" of closes actually serializes: trade 5's close begins only after trades 1–4 complete or time out.

**Black Swan 2 — Flash-crash gap with a stale trailing stop.** Price gaps through the local SL while the WS feed is mid-reconnect (backoff grows with `_reconnect_attempts`). Local exit logic (line 1054) requires a price tick to fire; no ticks → no local exit. The exchange-side protection is the SL attached at entry — but if the position has been trailed, the exchange stop was last updated by a `_broker_submit_checked` modify that may have failed (trade merely tagged `needs_manual_attention`, no retry, and the heartbeat that would repair it is dead code per V4.1). Result: a position protected only by an entry-time stop that the engine believes has been ratcheted to breakeven+.

**Black Swan 3 — Funding regime shift across the 0.05 boundary.** Funding spikes from 0.04 to 0.30 (displayed %). Normalized feature moves 0.04 → 0.003 — a 13× DROP in the feature as real funding rises 7.5×. The ensemble sees a funding collapse during a funding explosion, inverting any funding-driven signal exactly during the volatility event.

---

## Final Go/No-Go Decision: **NO-GO**

The build is materially better than the pre-remediation state (async modifies/closes, 429 backoff, WS reconnect hygiene, phantom-trade cleanup, close-failure re-arming are all real and correct). But it is not safe for live capital: two fund-safety P0s (dead SL heartbeat, silent ledger-save failure) and one signal-integrity P0 (funding normalization) survived remediation verbatim, and entries still block the event loop under the global lock.

### Exact code required to reach Go state

**Fix 1 — SL heartbeat (line 978), one token:**
```python
# BEFORE
if now - getattr(self, 'last_sl_heartbeat', now) > 60:
# AFTER
if now - getattr(self, 'last_sl_heartbeat', 0.0) > 60:
```

**Fix 2 — Ledger save failures must be loud (lines 651–652):**
```python
# BEFORE
            except Exception:
                pass
# AFTER
            except Exception as e:
                print(f"[TradeTracker] [CRITICAL] save_history FAILED — ledger may be stale: {e}")
                log_live_event(f"Ledger persistence failure: {e}", "CRITICAL")
```

**Fix 3 — Source-based funding normalization (lines 1387–1393):**
```python
        # Coinglass DOM always displays percentage (0.01 == 0.01%). Divide
        # unconditionally by source, never by magnitude (non-monotonic bug).
        if source == "coinglass_dom":
            return raw_funding / 100.0
        # coinglass_api ambiguous: keep magnitude heuristic as last resort
        if abs(raw_funding) >= 0.05:
            return raw_funding / 100.0
        return raw_funding
```
*Note:* this changes feature scale for live funding. The model must be retrained (or the backtest feature pipeline confirmed to use the same `/100`) before deploying, otherwise Fix 3 itself creates divergence. Verify with one parity run after the change.

**Fix 4 — Release the lock during order placement in `trigger_entry` (line 815):** compute sizing and insert the trade record under the lock, then release it for the broker round trip, then re-acquire to commit:
```python
            # ... trade record inserted into self.active_trades under self.lock ...
        # Lock RELEASED here — broker round trip must not block the engine
        try:
            broker_res = self.broker.execute_trade(symbol, direction, entry_price, sl, tp, strategy)
        except Exception as e:
            print(f"[TradeTracker] execute_trade raised for {symbol} ({strategy}): {e} — aborting phantom trade.")
            with self.lock:
                self.active_trades.pop(trade_id, None)
            return
        with self.lock:
            if trade_id not in self.active_trades:
                return  # closed/purged while order was in flight
            # ... existing broker_res handling, then self.save_history() ...
```
(The trade record already exists before dispatch, so `check_exits`/`reconcile` see it as `is_pending`-equivalent; set `"is_pending": True` in the initial record and clear it on confirmation to make this explicit.)

**Fix 5 — Deterministic executor + ledger shutdown (in `sig_handler` / `finally`, line 4709):**
```python
        finally:
            print("[Setup] Cleaning up tasks and closing browser...")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            try:
                trade_tracker.save_history()
                trade_tracker.broker_executor.shutdown(wait=True, cancel_futures=False)
                trade_tracker.emergency_executor.shutdown(wait=True, cancel_futures=False)
            except Exception as e:
                print(f"[Exit] Executor/ledger shutdown error: {e}")
            for c in (ctx1, ctx2):
                try:
                    if c:
                        await c.close()
                except Exception:
                    pass
```

**Fix 6 — Move `get_account_details()` out of the locked region in `make_close_cb` (line 1103):** fetch the balance BEFORE `with self.lock:` in the callback, then assign inside the lock.

### Post-fix gate before live capital
1. Re-run the 333-check parity suite after Fix 3 (expected: funding-feature checks change — that is the point).
2. Testnet soak ≥ 48h with `BINANCE_USE_TESTNET=true`, verifying: at least one SL-heartbeat push observed in logs, one forced `save_history` failure (chmod the file) produces the CRITICAL log, and one SIGTERM leaves zero live threads (`threading.enumerate()` at exit).
3. Chaos drill: block outbound REST mid-emergency-halt and confirm the event loop keeps processing ticks (Fixes 4 + the V1.2 collection pattern).

**Verdict: NO-GO until Fixes 1–4 land (Fixes 5–6 strongly recommended in the same pass). Fixes 1 and 2 are one-line fund-safety changes and should be committed immediately regardless of the deployment decision.**
