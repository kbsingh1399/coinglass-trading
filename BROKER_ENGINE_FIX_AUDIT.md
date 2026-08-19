# Broker & Engine Fix Verification Audit

**Date:** 2026-08-19  
**Branch:** `arena/019fec7a-coinglass-trading` (commit `84bde7d`)  
**Auditor:** Arena.ai Agent  

---

## Verification Summary

| # | Fix | Severity | Status | Details |
|---|-----|----------|--------|---------|
| 1 | IOC Fallback with 50bps Slippage Collar | CRITICAL | ❌ **NOT APPLIED** | Fallback still uses plain `MARKET` orders with no price limit |
| 2 | Stop Loss Order Wipes | HIGH | ⚠️ **PARTIALLY APPLIED** | `_cancel_all_orders` is per-symbol (correct), but `close_position()` still wipes ALL orders for the symbol |
| 3 | Single-Trade-Per-Symbol Barrier | HIGH | ❌ **NOT APPLIED** | Only blocks same-strategy duplicates; different strategies can still stack on same symbol |
| 4 | Trailing Stop at 5.0 ATR | MEDIUM | ❌ **NOT APPLIED** | Still activates at `2.0 * entry_atr` (2R), not 5R |
| 5 | Minimum Stop Floor | MEDIUM | ✅ **APPLIED (BETTER)** | `MIN_STOP_PCT` dict with adaptive widening (widens SL instead of rejecting) |
| 6 | Z-Score Variance Collapse | MEDIUM | ❌ **NOT APPLIED** | Static `1e-9` guard (not dynamic floor), no `[-9.9, 9.9]` clamp in `fmt_z()` |

**Score: 1 of 6 fully applied, 1 partially applied, 4 not applied.**

---

## Detailed Findings

### Fix 1: IOC Fallback with Slippage Collar — NOT APPLIED

**Location:** `binance_broker.py` → `execute_trade()` → GTX timeout fallback

**Current code (lines ~340-350):**
```python
# Fallback to MARKET
mkt_params = {
    "symbol": binance_symbol,
    "side": side,
    "type": "MARKET",          # ← NO slippage protection
    "quantity": self._format_qty(binance_symbol, slice_qty),
    "newClientOrderId": f"E1_{strategy}_{int(time.time_ns() % 1_000_000_000)}"
}
```

**Risk:** During a flash crash, the GTX limit times out after 3 seconds, and the fallback MARKET order fills at whatever the exchange book offers. In the March 2020 crash, BTC dropped 30% in minutes — a MARKET order during that window could fill at -15% from signal price.

**Required fix:** Replace with IOC + 50bps collar:
```python
# IOC fallback with strict 50bps slippage collar
MAX_SLIPPAGE_BPS = 50  # 0.50%
limit_px = entry_price * (1 + MAX_SLIPPAGE_BPS / 10000) if direction == 1 \
           else entry_price * (1 - MAX_SLIPPAGE_BPS / 10000)
ioc_params = {
    "symbol": binance_symbol,
    "side": side,
    "type": "LIMIT",
    "timeInForce": "IOC",
    "quantity": self._format_qty(binance_symbol, slice_qty),
    "price": self._format_price(binance_symbol, limit_px),
}
```

---

### Fix 2: Stop Loss Order Wipes — PARTIALLY APPLIED

**Location:** `binance_broker.py` → `close_position()`

**Current code:**
```python
def close_position(self, symbol, reason):
    self._cancel_all_orders(symbol)  # Cancels ALL orders for this symbol
    # ... then places market close order
```

**Assessment:** The `_cancel_all_orders` is scoped to the specific symbol, not global. This is correct for single-position-per-symbol. However, if multiple strategies open positions on the same symbol (which Fix 3 is supposed to prevent but doesn't), closing one position would cancel the other's trailing stops.

**Verdict:** Correct for the intended single-position model, but dependent on Fix 3 being applied.

---

### Fix 3: Single-Trade-Per-Symbol Barrier — NOT APPLIED

**Location:** `Engine_1.py` → `trigger_entry()`

**Current code:**
```python
strategy_trades = [t for t in self.active_trades.values() if t['strategy'] == strategy]
if any(t['symbol'] == symbol for t in strategy_trades):
    return  # Only blocks same-strategy duplicates
```

**Risk:** S1, S2, S3, S5, and S6 all have overlapping core conditions (`mc > 0, p8 < -0.2`). On a strong pullback, 3-4 strategies can fire simultaneously on the same symbol, creating 3-4× the intended position size.

**Required fix:** Add a global per-symbol barrier BEFORE the per-strategy check:
```python
# Global single-trade-per-symbol barrier
if any(t['symbol'] == symbol for t in self.active_trades.values()):
    log_live_event(f"Entry blocked: {symbol} already has an active position", "RiskGov")
    return
```

---

### Fix 4: Trailing Stop at 5.0 ATR — NOT APPLIED

**Location:** `Engine_1.py` → `check_exits()`

**Current code:**
```python
trail_activate_at = 2.0 * entry_atr if entry_atr > 0 else tp_dist
```

**Assessment:** The current 2R activation is actually reasonable for a ratcheting trail — it starts trailing before the TP target is reached, which is the correct behavior for locking in profits. Activating at 5R would mean the trail only starts when price has already reached the TP target (5× ATR), making it pointless since the trade would close at TP first.

**However:** If the intent is to prevent premature trailing during normal noise, the fix should be:
- Increase `trail_dist` from `1.0 * entry_atr` to `1.5 * entry_atr` (wider trail)
- OR keep activation at 2R but add a minimum profit lock (e.g., don't trail below entry + 0.5 ATR)

---

### Fix 5: Minimum Stop Floor — APPLIED (BETTER THAN DESCRIBED)

**Location:** `Engine_1.py` → `trigger_entry()`

**Current implementation:**
```python
MIN_STOP_PCT = {
    'BTCUSDT': 0.0008, 'ETHUSDT': 0.0008, ...
    'DOGEUSDT': 0.002, 'NATGASUSDT': 0.003,
}
min_stop_dist = entry_price * min_stop_pct
if stop_dist < min_stop_dist:
    stop_dist = min_stop_dist  # Adaptive widening instead of rejection
```

**Assessment:** This is BETTER than the described fix (which rejects the trade entirely). Adaptive widening preserves the entry opportunity while ensuring a safe minimum stop distance. ✅

---

### Fix 6: Z-Score Variance Collapse — NOT APPLIED

**Location:** `Engine_1.py` → `render_table()` → z-score computation and `fmt_z()`

**Current code:**
```python
# Computation: static 1e-9 guard (not dynamic)
if std_c > 1e-9:
    z_price_val = (price - mean_c) / std_c

# Display: no clamp
def fmt_z(z: float, fresh: bool = True) -> str:
    if z >= 2.0:
        return f"[bold red]{z:+.1f}σ[/bold red]"
    # ... no upper bound
```

**Risk:** During flat periods (e.g., weekend for commodities), std decays to near-zero. A value of `std = 1e-8` passes the `1e-9` guard but produces `z = 25684.9σ`, which corrupts the dashboard display and could trigger false drift detector blocks.

**Required fix:**
```python
# Dynamic volatility floor
VOL_FLOOR_FACTOR = 1e-6
std_floor = abs(mean_c) * VOL_FLOOR_FACTOR if mean_c != 0 else 1e-9
effective_std = max(std_c, std_floor)
z_price_val = (price - mean_c) / effective_std

# Clamp in fmt_z
def fmt_z(z: float, fresh: bool = True) -> str:
    z = max(-9.9, min(9.9, z))  # Clamp to [-9.9, 9.9]
    # ... rest of formatting
```

---

## Implementation Plan

All 5 missing fixes can be applied in a single commit touching 2 files:

| File | Fixes | Lines Changed |
|------|-------|---------------|
| `binance_broker.py` | Fix 1 (IOC fallback) | ~10 lines |
| `Engine_1.py` | Fix 3 (single-trade barrier), Fix 4 (trail activation), Fix 6 (z-score floor + clamp) | ~20 lines |
