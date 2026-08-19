# Autonomous Bug Hunt Report — Week 1/2 Implementation Audit

**Date:** 2026-08-19  
**Branch:** `arena/019fec7a-coinglass-trading`  
**Auditor:** Arena.ai Agent (Autonomous Bug Hunt Loop — AGENTS.md Part 2)  
**Files Audited:** `Engine_1.py` (29 chunks), `six_strategy_engine.py` (7 chunks)

---

## EXECUTIVE SUMMARY

All four Week 1/2 implementations are **architecturally present and integrated**, but I found **7 bugs** ranging from CRITICAL to LOW. The most severe is that the `FeatureDriftDetector` is initialized with an empty training stats dict, making it a complete no-op — it will never block any prediction.

| # | Severity | Component | Issue |
|---|----------|-----------|-------|
| 1 | **CRITICAL** | FeatureDriftDetector | Initialized with `{}` — never blocks anything |
| 2 | **CRITICAL** | BinanceOIFeed | Returns contract-denominated OI, not USD — unit mismatch with Parquet |
| 3 | **HIGH** | DOM Scraper | Still extracts OI + liquidations, overwriting clean Binance feeds |
| 4 | **HIGH** | CoinglassNormalizer | Funding rate threshold misclassifies 0.001–0.01 range |
| 5 | **HIGH** | forceOrder Accumulator | Global `last_15m_idx` causes cross-symbol premature reset |
| 6 | **MEDIUM** | CoinglassNormalizer | CVD reset threshold (50%) too aggressive for low-volume altcoins |
| 7 | **LOW** | parse_float | NaN return silently dropped by `finite_float_or_none`, leaving stale values |

---

## FINDING 1: FeatureDriftDetector Is a No-Op (CRITICAL)

**Location:** `six_strategy_engine.py` — `LiveSixStrategyPredictor.__init__()`

**Root Cause:**
```python
self.drift_detector = FeatureDriftDetector({})  # Empty training stats!
```

The `FeatureDriftDetector` class is correctly implemented with 4σ z-score logic, but it's initialized with an **empty dictionary**. When `check_row()` is called:

```python
def check_row(self, symbol, features):
    sym_stats = self.stats.get(symbol, {})  # Always returns {}
    if not sym_stats:
        return True, []  # ALWAYS returns safe — never blocks!
```

**Impact:** The drift detector will **never block any prediction**, regardless of how extreme the feature values are. The entire Week 2 implementation is dead code.

**Fix:** Load training stats from Parquet data during initialization:

```python
def __init__(self, symbols: List[str]):
    # ... existing code ...
    
    # Load training stats from Parquet for drift detection
    training_stats = self._load_training_stats(symbols)
    self.drift_detector = FeatureDriftDetector(training_stats)

def _load_training_stats(self, symbols: List[str]) -> Dict:
    """Compute mean/std for critical features from backtesting Parquet data."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "backtesting_data")
    stats = {}
    critical_features = ['cvd_d', 'zc4', 'zc10', 'zc20', 'zoi', 'liql', 'liqs', 'fr', 'vr5']
    
    for sym in symbols:
        summary_path = os.path.join(data_dir, f"Master_{sym}_15m_Final_Summary.parquet")
        if not os.path.exists(summary_path):
            continue
        try:
            df = pd.read_parquet(summary_path)
            df = featurize(df.copy())
            sym_stats = {}
            for feat in critical_features:
                if feat in df.columns:
                    sym_stats[f'{feat}_mean'] = float(df[feat].mean())
                    sym_stats[f'{feat}_std'] = float(df[feat].std())
            if sym_stats:
                stats[sym] = sym_stats
        except Exception as e:
            print(f"[SixStrategy] Failed to load training stats for {sym}: {e}")
    
    print(f"[SixStrategy] Loaded drift detection stats for {len(stats)} symbols")
    return stats
```

---

## FINDING 2: BinanceOIFeed Returns Contracts, Not USD (CRITICAL)

**Location:** `Engine_1.py` — `BinanceOIFeed._fetch_oi()`

**Root Cause:**
```python
async def _fetch_oi(session, sym):
    async with session.get(url, params={"symbol": sym}, ...) as resp:
        data = await resp.json()
        oi_str = data.get("openInterest")  # This is in CONTRACTS (base asset qty)
        if oi_str:
            await self.store.update(sym, source="binance_oi", oi=float(oi_str))
```

The Binance `/fapi/v1/openInterest` endpoint returns open interest in **contracts** (base asset quantity). For BTCUSDT, this might be `123,456` contracts. But the backtesting Parquet data's `Agg. OI` column comes from Coinglass's "Aggregated Open Interest (STABLECOIN-margined, Candles)" indicator, which is in **USD notional** (e.g., `$5,678,901,234`).

**Impact:** The `zoi` z-score feature in `featurize()` will see values that are ~$50,000× smaller than the training distribution (for BTC). The z-score will be permanently at -10σ or worse, triggering constant drift blocks once Finding 1 is fixed.

**Fix:** Multiply by the current price to convert contracts to USD notional:

```python
async def _fetch_oi(self, session: aiohttp.ClientSession, sym: str) -> None:
    try:
        params = {"symbol": sym}
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            if resp.status == 200:
                data = await resp.json()
                oi_contracts = float(data.get("openInterest", 0))
                if oi_contracts > 0:
                    # Get current price from snapshot to convert to USD notional
                    snap = self.store._data.get(sym)
                    price = snap.price if snap and snap.price > 0 else 0.0
                    if price > 0:
                        oi_usd = oi_contracts * price
                        await self.store.update(sym, source="binance_oi", oi=oi_usd)
                    else:
                        # No price available — store raw contracts with warning
                        await self.store.update(sym, source="binance_oi", oi=oi_contracts)
    except Exception:
        pass
```

---

## FINDING 3: DOM Scraper Still Overwrites Binance Feeds (HIGH)

**Location:** `Engine_1.py` — `SINGLE_FRAME_EXTRACTION_JS` (chunk 12) and `poll_loop` field_map

**Root Cause:** The JavaScript extraction code still parses `open_interest` and `liquidations_long/short` from the Coinglass DOM:

```javascript
} else if (upper.includes('OPEN INTEREST') || /\bOI\b/.test(upper)) {
    if (allTextNums.length > 0) data.open_interest = allTextNums[allTextNums.length - 1];
} else if (upper.includes('LIQUIDATION') || upper.includes('LIQ')) {
    // ... extracts liquidations_long and liquidations_short
}
```

And the `poll_loop` field_map still routes these to the snapshot:

```python
field_map = {
    "open_interest": "oi",
    "liquidations_long": "liq_long",
    "liquidations_short": "liq_short",
    # ...
}
```

**Impact:** Every 500ms, the DOM scraper overwrites the clean Binance OI and liquidation values with potentially stale, cumulative, or viewport-relative Coinglass values. The `BinanceOIFeed` (15s poll) and `forceOrder` WebSocket (real-time) are fighting a losing battle against the DOM scraper's 2 Hz overwrite rate.

**Fix:** Remove OI and liquidation extraction from the DOM JS and field_map:

```javascript
// REMOVE these blocks from SINGLE_FRAME_EXTRACTION_JS:
// } else if (upper.includes('OPEN INTEREST') || /\bOI\b/.test(upper)) { ... }
// } else if (upper.includes('LIQUIDATION') || upper.includes('LIQ')) { ... }
```

```python
# REMOVE from poll_loop field_map:
# "open_interest": "oi",
# "liquidations_long": "liq_long",
# "liquidations_short": "liq_short",
```

Also remove from the `_route_payload` API interception path:
```python
# In _route_payload, REMOVE:
# elif "open-interest" in url:
#     await self._apply(payload, "oi")
# elif "liquidation" in url:
#     await self._apply_liq(payload)
```

---

## FINDING 4: Funding Rate Threshold Misclassification (HIGH)

**Location:** `Engine_1.py` — `CoinglassNormalizer.normalize_funding()`

**Root Cause:**
```python
def normalize_funding(self, raw_funding: float) -> float:
    if abs(raw_funding) >= 0.01:      # 1% — divide by 100
        return raw_funding / 100.0
    if abs(raw_funding) >= 0.001:     # 0.1% — ALSO divide by 100
        return raw_funding / 100.0
    return raw_funding                 # < 0.1% — keep as-is
```

**The problem:** Funding rates between 0.001 and 0.01 (0.1% to 1%) are ambiguously classified. Consider these real-world scenarios:

| Coinglass Display | Parsed Value | Correct Decimal | normalize_funding() Output | Correct? |
|---|---|---|---|---|
| "0.0100%" | 0.0100 | 0.0001 | 0.0001 | ✅ |
| "0.0500%" | 0.0500 | 0.0005 | 0.0005 | ✅ |
| "0.0050" (decimal) | 0.0050 | 0.0050 | 0.00005 | ❌ (divided by 100 when it shouldn't be) |
| "0.0010" (decimal) | 0.0010 | 0.0010 | 0.00001 | ❌ (divided by 100 when it shouldn't be) |

**Impact:** When Coinglass sends funding rate as a decimal fraction (0.005 = 0.5%), the normalizer incorrectly divides it by 100, producing 0.00005 instead of 0.005. This is 100× too small, corrupting the `zfr` z-score feature.

**Fix:** Use the source tag to determine normalization, not the value magnitude:

```python
def normalize_funding(self, raw_funding: float, source: str = "coinglass_dom") -> float:
    """Single-pass normalization based on source, not value magnitude.
    
    Coinglass DOM: always displays as percentage (0.01 = 0.01%)
    Coinglass API: sometimes percentage, sometimes decimal
    Binance API: always decimal fraction (0.0001 = 0.01%)
    """
    if source == "binance":
        return raw_funding  # Already in decimal fraction
    
    # Coinglass: if value looks like a percentage (> 0.05 = 5%), divide by 100
    # Funding rates rarely exceed 5% even in extreme conditions
    if abs(raw_funding) >= 0.05:
        return raw_funding / 100.0
    
    # Value is already in decimal fraction format
    return raw_funding
```

---

## FINDING 5: forceOrder Accumulator Cross-Symbol Race (HIGH)

**Location:** `Engine_1.py` — `BinanceTradePriceWebSocketFeed.run()`

**Root Cause:**
```python
# Global state — shared across ALL symbols
self.last_15m_idx: int = 0

# In the message handler:
current_15m = evt_time // (15 * 60 * 1000)
if current_15m != self.last_15m_idx:
    self.last_15m_idx = current_15m
    self.liq_long_accum.clear()   # Clears ALL symbols!
    self.liq_short_accum.clear()  # Clears ALL symbols!
```

**The race condition:**
1. T=0: BTC liquidation arrives in 15m window N → `last_15m_idx = N`, accumulators have BTC data
2. T=1: ETH liquidation arrives in 15m window N → `current_15m == last_15m_idx`, no reset, ETH accumulates correctly
3. T=900: BTC liquidation arrives in 15m window N+1 → `current_15m != last_15m_idx`, **ALL accumulators cleared** including ETH's window N data
4. T=901: ETH's last liquidation from window N arrives → accumulator was already cleared, data lost

**Impact:** Liquidation data for slower-trading altcoins (ADA, DOGE, TRX) is frequently lost when a high-frequency symbol (BTC, ETH) triggers the 15m boundary first.

**Fix:** Use per-symbol 15m tracking:

```python
# Replace global last_15m_idx with per-symbol dict
self.last_15m_per_sym: Dict[str, int] = {}

# In the forceOrder handler:
if event_type == "forceOrder":
    o = data.get("o", {})
    side = o.get("S")
    qty = finite_float_or_none(o.get("q"))
    evt_time = o.get("T", data.get("E", 0))
    if qty and side and evt_time:
        current_15m = evt_time // (15 * 60 * 1000)
        sym_last_15m = self.last_15m_per_sym.get(sym, 0)
        
        if current_15m != sym_last_15m:
            # New 15m window for THIS symbol only
            self.last_15m_per_sym[sym] = current_15m
            self.liq_long_accum[sym] = 0.0
            self.liq_short_accum[sym] = 0.0
        
        if side == "SELL":
            self.liq_long_accum[sym] += qty
        elif side == "BUY":
            self.liq_short_accum[sym] += qty
        
        await self.store.update(
            sym, source="binance_ws",
            liq_long=self.liq_long_accum[sym],
            liq_short=self.liq_short_accum[sym]
        )
    continue
```

---

## FINDING 6: CVD Reset Threshold Too Aggressive for Altcoins (MEDIUM)

**Location:** `Engine_1.py` — `CoinglassNormalizer.normalize_cvd()`

**Root Cause:**
```python
if accumulated != 0 and abs(delta) > abs(accumulated) * 0.5:
    # Reset detected — re-baseline
    return accumulated  # Return old value, ignore new
```

For low-volume altcoins like TRXUSDT or DOGEUSDT, the accumulated CVD might be small (e.g., 50,000). A single large trade of 30,000 contracts would produce `delta = 30,000`, which is 60% of `accumulated = 50,000`, triggering a false reset detection. The legitimate trade is silently dropped.

**Fix:** Add a minimum absolute threshold to prevent false positives on small accumulators:

```python
# Only detect reset if delta is both > 50% of accumulated AND > a minimum absolute value
MIN_RESET_THRESHOLD = {
    'BTCUSDT': 500_000, 'ETHUSDT': 200_000, 'BNBUSDT': 50_000,
    'SOLUSDT': 50_000, 'XRPUSDT': 100_000, 'DOGEUSDT': 200_000,
    'ADAUSDT': 100_000, 'TRXUSDT': 200_000, 'LINKUSDT': 20_000,
    'AVAXUSDT': 10_000, 'DOTUSDT': 10_000, 'LTCUSDT': 5_000,
    'NEARUSDT': 20_000, 'SUIUSDT': 20_000,
}

min_thresh = MIN_RESET_THRESHOLD.get(symbol, 50_000)
if accumulated != 0 and abs(delta) > abs(accumulated) * 0.5 and abs(delta) > min_thresh:
    # True reset detected
    baseline_dict[symbol] = raw_cvd
    last_raw_dict[symbol] = raw_cvd
    return accumulated
```

---

## FINDING 7: parse_float NaN Silently Dropped (LOW)

**Location:** `Engine_1.py` — `parse_float()` and `SnapshotStore.update()`

**Root Cause:**
```python
def parse_float(val: Any) -> float:
    if isinstance(val, str) and val.strip().upper() in ("N/A", "-", "--", ""):
        return float('nan')  # Returns NaN
    res = _parse_suffix_float(val)
    return res if res is not None else float('nan')
```

In `SnapshotStore.update()`:
```python
fv = finite_float_or_none(v)  # Returns None for NaN
if fv is None:
    continue  # Silently skips — leaves OLD value in snapshot
```

**Impact:** When the DOM scraper returns "N/A" for an indicator (e.g., CVD temporarily unavailable), the NaN is silently dropped and the **previous value remains in the snapshot**. This means stale data persists indefinitely until a valid value arrives. For CVD, this could mean the last known CVD value (potentially from before a page reload) persists for minutes.

**Fix:** Explicitly set stale indicators to 0.0 when N/A is received, or track staleness separately:

```python
# In SnapshotStore.update(), for indicator fields:
elif k in ("fut_cvd", "spot_cvd", "liq_long", "liq_short", ...):
    fv = finite_float_or_none(v)
    if fv is None:
        # N/A received — mark as stale but don't corrupt with old value
        # Set to 0.0 to prevent stale data from triggering false signals
        if source == "coinglass":
            fv = 0.0  # Reset to zero on N/A
        else:
            continue  # Binance sources: skip N/A (they rarely send it)
```

---

## REMAINING WEEK 3/4 RECOMMENDATIONS

### Week 3: Data Pipeline Hardening

1. **Training Stats Loader** — Implement `_load_training_stats()` to populate `FeatureDriftDetector` from Parquet data. Without this, the drift detector is useless (Finding 1).

2. **OI Unit Conversion** — Convert Binance contract-denominated OI to USD notional using live price (Finding 2).

3. **DOM Scraper Cleanup** — Remove OI and liquidation extraction from JS and field_map (Finding 3). Add a `source_priority` dict to `SnapshotStore.update()` that rejects lower-priority sources:
   ```python
   SOURCE_PRIORITY = {
       "oi": {"binance_oi": 10, "coinglass": 1},
       "liq_long": {"binance_ws": 10, "coinglass": 1},
       "liq_short": {"binance_ws": 10, "coinglass": 1},
       "funding": {"binance_funding": 10, "coinglass": 5},
   }
   ```

4. **Per-Symbol Liquidation Accumulators** — Fix the cross-symbol race condition in forceOrder handler (Finding 5).

5. **Funding Rate Source Tagging** — Pass `source` parameter to `normalize_funding()` to eliminate value-based ambiguity (Finding 4).

### Week 4: Production Readiness

6. **Drift Detector Calibration** — After loading training stats, run a dry-run for 24 hours logging all drift blocks without actually blocking. Tune the 4σ threshold and `MAX_DRIFT_BEFORE_BLOCK` based on observed false positive rate.

7. **CVD Accumulator Persistence** — Save `_cvd_accumulated` dict to disk on shutdown and reload on startup. Currently, every engine restart resets the CVD accumulator, causing a massive `cvd_d` spike on the first bar.

8. **Binance Funding Rate Feed** — Add a dedicated `BinanceFundingFeed` that polls `/fapi/v1/fundingRate` every 8 hours (at settlement time). This eliminates all Coinglass funding rate normalization issues.

9. **End-to-End Parity Test** — Build a test that takes the last 100 rows of Parquet data, feeds them through `featurize()` + `predict_ensemble()`, and compares the output against the live engine's predictions for the same candle. Any divergence > 0.01 in probability indicates a remaining data pipeline issue.

10. **Monitoring Dashboard** — Add a `/health` endpoint that exposes:
    - Drift detector block count per symbol (last 1h)
    - CVD accumulator values vs. Coinglass DOM values (divergence check)
    - OI conversion factor (price used for contract→USD)
    - forceOrder accumulator age per symbol (detect stale data)
    - Funding rate last-seen timestamp per source

---

*Audit conducted by static analysis of 29 chunks of Engine_1.py and 7 chunks of six_strategy_engine.py fetched from GitHub raw content. No runtime execution was performed.*
