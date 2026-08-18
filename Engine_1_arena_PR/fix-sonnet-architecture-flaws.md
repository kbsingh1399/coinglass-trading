# Sonnet Architecture Fixes

## Goal
Implement the architectural fixes discovered during Sonnet's deep systems review of the trading engine, specifically focusing on the most critical failure modes that could lead to financial loss during live execution.

## Phase 1: Execution & Risk Logic (P0)
These fixes address the immediate execution bugs that leave positions unprotected.

### 1. Fix the "Naked Position" Trap in `engine_components/binance_broker.py`
**Problem:** `close_position()` cancels all protective SL/TP orders *before* attempting the market close order. If the market close fails due to Binance 500 errors, the position is left completely naked.
**Fix:**
- Move `self._cancel_all_orders(symbol)` to *after* the `POST /fapi/v1/order` succeeds and returns a valid `orderId`.
- This ensures the position is protected by the exchange-side SL until the exact millisecond it is successfully closed.

### 2. Dedicated Emergency Executor in `Engine_1.py`
**Problem:** `LiveTradeTracker` uses a single-worker `ThreadPoolExecutor` for all broker commands. A slow, retrying SL heartbeat blocks emergency position closes during market crashes.
**Fix:**
- Add `self.emergency_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="BinanceEmergency")` in `LiveTradeTracker.__init__`.
- Route all `self.broker.close_position` calls (from `check_exits`, orphan guards, etc.) to the `emergency_executor` instead of the routine `broker_executor`.

## Phase 2: Data Pipeline Integrity (P1)
These fixes address the silent feature corruption that ruins ML inputs.

### 3. Safe Value Defaulting in `Engine_1.py`
**Problem:** `parse_float()` silently defaults failed DOM reads to `0.0`, which severely corrupts indicators like EMA, generating false ML signals.
**Fix:**
- Update `parse_float()` to return `None` (or `np.nan`) on failure instead of `0.0`.
- Update the `candle_data` dictionary build to use forward-fill logic for missing critical indicators so the last known good value is used, or explicitly fail the bar creation if no historical value exists.

---

## 🎼 Orchestration Details
**Agents that will be invoked in parallel during implementation (Phase 2):**
- `@backend-specialist`: To implement the ThreadPoolExecutor changes and fix the `binance_broker.py` cancel sequence.
- `@database-architect` (Data Pipeline): To patch the `parse_float` and DOM extraction handlers in `Engine_1.py`.
- `@test-engineer`: To verify that the broker correctly handles failures and doesn't cancel SLs prematurely.
