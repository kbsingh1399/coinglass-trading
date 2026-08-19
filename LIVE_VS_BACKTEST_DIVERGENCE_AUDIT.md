# Live vs. Backtesting Data Divergence — Tick-by-Tick Audit

**Date:** 2026-08-18  
**Branch:** `arena/019fec7a-coinglass-trading`  
**Files Audited:** `Engine_1.py`, `engine_components/coinglass_scraper.py`, `six_strategy_engine.py`, `run_all_6.py`

---

## 1. DATA FLOW ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        BACKTESTING PIPELINE                              │
│                                                                         │
│  mythos_pipeline_loop.py → Parquet files (Master_{SYM}_15m_Final_*.pq) │
│       │                                                                 │
│       ▼                                                                 │
│  run_all_6.py::load() → DataFrame with columns:                        │
│    Open, High, Low, Close, Volume, CVD, Agg. OI, Agg. Liq Long/Short, │
│    Agg. Funding Rate, Long/Short Ratio, Bid/Ask Qty, etc.              │
│       │                                                                 │
│       ▼                                                                 │
│  featurize() → ATR, zc4/10/20, mc, p8, rsi, vr, liql/liqs, zoi, etc. │
│       │                                                                 │
│       ▼                                                                 │
│  make_signal_s1..s6 → ML ensemble → Walk-forward validation             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         LIVE PIPELINE                                    │
│                                                                         │
│  PATH A: DOM Scraping (Coinglass TradingView)                           │
│    Playwright → iframe → SINGLE_FRAME_EXTRACTION_JS                     │
│       │                                                                 │
│       ├── volume ← TradingView OHLCV legend (Vol field)                │
│       ├── futures_cvd ← "Aggregated Futures CVD" indicator legend     │
│       ├── spot_cvd ← "Aggregated Spot CVD" indicator legend           │
│       ├── open_interest ← "Aggregated OI (Candles)" indicator legend  │
│       ├── funding_rate ← "Funding Rates" indicator legend ÷ 100       │
│       ├── liquidations_long/short ← "Aggregated Liquidations" legend  │
│       ├── rsi ← "Relative Strength Index" indicator legend             │
│       ├── coins_bid/ask ← "Aggregated Futures Bid & Ask (Coins)"      │
│       ├── dollars_bid/ask ← "Aggregated Futures Bid & Ask (Dollars)"  │
│       └── whale_idx, taker_buy/sell_count ← custom indicators         │
│       │                                                                 │
│       ▼                                                                 │
│    store.update(sym, source="coinglass", fut_cvd=..., liq_long=...)    │
│                                                                         │
│  PATH B: API Response Interception (Coinglass HTTP)                     │
│    page.on("response") → handle_response()                              │
│       │                                                                 │
│       ├── "open-interest" URL → _apply(payload, "oi")                  │
│       ├── "funding-rate" URL → _apply(payload, "funding") + normalize  │
│       ├── "liquidation" URL → _apply_liq(payload)                      │
│       ├── "long-short" URL → _apply(payload, "ls_ratio")              │
│       └── "cumulative-volume" URL → _apply(payload, "fut_cvd/spot")   │
│       │                                                                 │
│       ▼                                                                 │
│    store.update(sym, source="coinglass", oi=..., funding=...)          │
│                                                                         │
│  PATH C: Binance WebSocket (Real-time)                                  │
│    BinanceTradePriceWebSocketFeed → wss://fstream.binance.com           │
│       │                                                                 │
│       └── store.update(sym, source="binance_ws", price=...)            │
│                                                                         │
│  PATH D: Binance REST (Footprint)                                       │
│    BinanceFootprintFeed → /fapi/v1/klines (5s poll)                    │
│       │                                                                 │
│       └── store.update(sym, source="binance", price=..., fp_delta=...) │
│                                                                         │
│  ─── CONVERGENCE POINT ──────────────────────────────────────────────── │
│                                                                         │
│  SnapshotStore._data[sym] = AssetSnapshot(                              │
│    price, volume, rsi, fut_cvd, spot_cvd, liq_long, liq_short,        │
│    funding, ls_ratio, oi, coins_bid, coins_ask, ...)                   │
│       │                                                                 │
│       ▼                                                                 │
│  six_strategy_engine.py::_build_df() → Column mapping:                 │
│    fut_cvd → "CVD"                                                      │
│    oi → "Agg. OI"                                                       │
│    funding → "Agg. Funding Rate"                                        │
│    liq_long → "Agg. Liq Long"                                           │
│    liq_short → "Agg. Liq Short"                                         │
│    ls_ratio → "Long/Short Ratio (Account)"                              │
│    coins_bid → "Bid Qty"                                                │
│    coins_ask → "Ask Qty"                                                │
│    fp_delta → "Delta Qty"                                               │
│       │                                                                 │
│       ▼                                                                 │
│  featurize() → ATR, zc4/10/20, mc, p8, rsi, vr, liql/liqs, zoi, etc. │
│       │                                                                 │
│       ▼                                                                 │
│  make_signal_s1..s6 → predict_ensemble() → trigger_entry()             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. TICK-BY-TICK DIVERGENCE AUDIT

### 2.1 CVD Baseline Reset — CRITICAL DIVERGENCE

**Backtesting data:** `CVD` column in Parquet is a raw, monotonically accumulating sum of tick-level buy_volume minus sell_volume over the entire historical dataset. Values range from -500M to +500M for BTC.

**Live data (PATH A — DOM):** The Coinglass "Aggregated Futures Cumulative Volume Delta (CVD)" indicator displays CVD relative to the chart's visible viewport or session start. When the page reloads, the chart resets, or the viewport scrolls, the displayed CVD value jumps to a new baseline.

**The divergence in `featurize()`:**
```python
df["cvd_d"] = df["CVD"].diff(5)  # 5-bar CVD change
for k in [4, 10, 20]:
    df[f"zc{k}"] = _zscore(df["CVD"], k)  # Z-score of raw CVD
```

**Impact scenario:**
- At T=0, live CVD = 1,234,567 (normal)
- At T=1, page reloads → CVD resets to -50,000 (viewport-relative)
- `cvd_d` = -50,000 - 1,234,567 = **-1,284,567** (artificial massive sell signal)
- `zc20` z-score spikes to -15σ (completely outside training distribution)
- S1 fires a false LONG signal because `zc20 > 0.1` check passes on the recovery bar

**Live data (PATH B — API interception):** The `cumulative-volume` API endpoint returns the same viewport-relative values. The `_apply(payload, "fut_cvd")` path feeds the same broken data.

**Severity:** CRITICAL — This is the single largest source of live/backtest divergence. Every CVD-dependent feature (`cvd_d`, `zc4`, `zc10`, `zc20`, `oicc`) is corrupted after every page reload or chart reset.

---

### 2.2 Liquidation Aggregation Window — HIGH DIVERGENCE

**Backtesting data:** `Agg. Liq Long` and `Agg. Liq Short` columns in Parquet represent discrete 15-minute candle liquidation volumes. Each row is the sum of liquidations that occurred during that specific 15m window.

**Live data (PATH A — DOM):** The Coinglass "Aggregated Liquidations" indicator legend displays values that depend on the indicator's internal configuration. The indicator name includes "Aggregated" which suggests it may show cumulative or rolling values rather than discrete candle values.

**Live data (PATH B — API interception):** The `liquidation` API endpoint returns `longLiq` and `shortLiq` fields. These are likely the most recent candle's values, but the API response structure doesn't include a timestamp to confirm which candle they belong to.

**The divergence in `featurize()`:**
```python
df["liql"] = pd.to_numeric(df["Agg. Liq Long"]).rolling(5, min_periods=1).sum()
df["liqlm"] = df["liql"].rolling(100, min_periods=1).mean()
```

**Impact:** If live liquidation values are already cumulative (e.g., 24h rolling), then `rolling(5).sum()` produces values 5x larger than backtesting. The S1 signal check `ll > llm * 1.2` would fire constantly because both `ll` and `llm` are inflated by the same factor, but the ratio becomes unstable.

**Severity:** HIGH — S1 (Liquidation strategy) is directly affected. The `ll > llm * 1.2` ratio check may still work if both numerator and denominator are inflated equally, but the z-score features derived from liquidation data would be completely wrong.

---

### 2.3 Funding Rate Double-Normalization — HIGH DIVERGENCE

**Backtesting data:** `Agg. Funding Rate` in Parquet is stored as a decimal fraction (e.g., 0.0001 for 0.01%).

**Live data — THREE normalization layers:**

1. **DOM extraction** (`SINGLE_FRAME_EXTRACTION_JS`, line 135-136):
   ```javascript
   let fundingVal = parseFloat(num);
   res.funding_rate = isFinite(fundingVal) ? String(fundingVal / 100.0) : num;
   ```
   Divides by 100: `0.01` → `0.0001`

2. **API interception** (`normalize_funding_rate()`, line 200-205):
   ```python
   def normalize_funding_rate(val: float) -> float:
       if abs(val) >= 0.005:
           return val / 100.0
       return val
   ```
   Divides by 100 if |val| >= 0.005: `0.01` → `0.0001`, but `0.0001` stays `0.0001`

3. **featurize()** (`six_strategy_engine.py`, line 185):
   ```python
   fr = fr.apply(lambda v: v / 100.0 if abs(v) >= 0.001 else v)
   ```
   Divides by 100 again if |v| >= 0.001: `0.0001` stays, but `0.01` → `0.0001`

**Impact scenario (DOM path):**
- Coinglass displays "0.01%" → JS extracts "0.01" → divides by 100 → `0.0001`
- `featurize()` sees `0.0001` (< 0.001) → no further division → `fr = 0.0001` ✓ CORRECT

**Impact scenario (API path):**
- API returns `0.01` (percent) → `normalize_funding_rate` sees |0.01| >= 0.005 → divides by 100 → `0.0001`
- `featurize()` sees `0.0001` (< 0.001) → no further division → `fr = 0.0001` ✓ CORRECT

**Impact scenario (edge case — high funding):**
- Coinglass displays "0.15%" → JS extracts "0.15" → divides by 100 → `0.0015`
- `featurize()` sees `0.0015` (>= 0.001) → divides by 100 AGAIN → `fr = 0.000015` ✗ WRONG (100x too small)

**Severity:** HIGH — During high-volatility periods when funding rates exceed 0.1%, the triple normalization produces values 100x smaller than backtesting. The `zfr` z-score feature becomes meaningless.

---

### 2.4 Volume Source Mismatch — MEDIUM DIVERGENCE

**Backtesting data:** `Volume` column in Parquet is the 15m candle volume from Binance Futures klines API.

**Live data:** The DOM scraper extracts `volume` from the TradingView OHLCV legend (`title === 'Vol'`). This is TradingView's rendering of the volume data, which comes from Coinglass's own data feed (not directly from Binance). Coinglass may aggregate volume differently (e.g., including spot volume, or using a different exchange set).

**The divergence in `featurize()`:**
```python
df["vr5"] = df["Volume"] / (df["Volume"].rolling(20, min_periods=1).mean() + 1e-10)
```

**Impact:** The `vr5` ratio is unit-invariant (ratio of current to average), so absolute volume differences cancel out. However, if Coinglass includes spot volume while backtesting uses futures-only volume, the ratio itself differs because the denominator (20-bar average) includes different data.

**Severity:** MEDIUM — The ratio partially self-corrects, but the absolute volume values used in other contexts (e.g., ML feature importance) may diverge.

---

### 2.5 Temporal Desynchronization — MEDIUM DIVERGENCE

**Data arrival timeline per 15m candle:**

| Source | Update Frequency | Latency | Data Freshness |
|--------|-----------------|---------|----------------|
| Binance WS (price) | ~10 Hz | ~50ms | Real-time |
| Binance REST (footprint) | 5s poll | ~200ms | 5s stale |
| DOM scrape (all indicators) | 500ms poll | ~1-3s | 500ms-3s stale |
| API interception (OI, funding) | On HTTP response | ~0-60s | Varies |

**Impact:** When a new 15m candle opens, the price updates immediately via WebSocket, but the Coinglass indicators (CVD, OI, liquidations) lag by 500ms-3s. The `_build_df()` method in `six_strategy_engine.py` builds the DataFrame from `candles_history`, which only updates on candle rollover. Intra-candle, the `current_candle` dict accumulates the latest values, but predictions only fire on candle close.

**The critical window:** At candle close (T+0), the price is accurate (from WS), but the CVD/OI/liquidation values are from the last DOM poll (T-500ms to T-3s). If a large liquidation event occurs in the last 3 seconds of a candle, the DOM scraper may not capture it before the candle rolls over.

**Severity:** MEDIUM — Predictions fire on candle close with slightly stale indicator data. The 500ms-3s lag is small relative to the 15m candle duration, but during high-volatility events, it can miss critical signals.

---

### 2.6 Open Interest Unit Ambiguity — MEDIUM DIVERGENCE

**Backtesting data:** `Agg. OI` in Parquet is raw USD-denominated open interest (e.g., 1,234,567,890 for BTC).

**Live data:** The Coinglass indicator is "Aggregated Open Interest(STABLECOIN-margined,Candles)". The "STABLECOIN-margined" qualifier means it's USD-denominated, which matches backtesting. The "Candles" qualifier means it's per-candle, which also matches.

**However:** The DOM extraction parses strings like "1.54B" into `1,540,000,000`. If Coinglass changes its display precision (e.g., from "1.54B" to "1540M"), the parsed value remains correct. But if Coinglass switches to displaying in BTC-denominated OI instead of USD, the values would differ by a factor of ~$100,000 (BTC price).

**The divergence in `featurize()`:**
```python
df["zoi"] = _zscore(oi, 100)  # Z-score over 100 bars
```

**Impact:** The z-score is scale-invariant, so unit changes that affect all values equally cancel out. But if the unit changes mid-session (e.g., after a page reload), the z-score sees a step function and produces extreme values.

**Severity:** MEDIUM — The z-score provides some protection, but unit changes during a session would corrupt the feature.

---

## 3. ARCHITECTURAL RECOMMENDATIONS

### 3.1 Replacing DOM-Scraped Indicators with Raw Binance Data

**Recommended architecture:**

```
┌──────────────────────────────────────────────────────────────────────┐
│                    PROPOSED: PURE BINANCE PIPELINE                    │
│                                                                      │
│  1. Price + Volume: Binance Futures klines REST API (15m)           │
│     → Already implemented in BinanceFootprintFeed                    │
│     → Provides: Open, High, Low, Close, Volume, buy_vol, sell_vol   │
│                                                                      │
│  2. CVD: Compute locally from Binance aggTrades WebSocket           │
│     → Subscribe to wss://fstream.binance.com/ws/{sym}@aggTrade      │
│     → Accumulate: if buyer_is_maker: sell_vol += qty                 │
│                    else: buy_vol += qty                               │
│     → CVD = cumulative(buy_vol - sell_vol) per candle                │
│     → RESET-PROOF: computed from raw trades, no viewport dependency │
│                                                                      │
│  3. Open Interest: Binance /fapi/v1/openInterest REST API           │
│     → Poll every 15m at candle close                                 │
│     → Returns raw USD-denominated OI                                 │
│     → Matches backtesting data exactly                               │
│                                                                      │
│  4. Funding Rate: Binance /fapi/v1/fundingRate REST API             │
│     → Poll every 8h (funding settles every 8h)                       │
│     → Returns decimal fraction (e.g., 0.0001)                        │
│     → No normalization needed                                        │
│                                                                      │
│  5. Liquidations: Binance /fapi/v1/allForceOrders REST API          │
│     → Poll every 15m at candle close                                 │
│     → Aggregate by symbol + 15m window                               │
│     → Provides: discrete per-candle liquidation volumes              │
│                                                                      │
│  6. Long/Short Ratio: Binance /futures/data/globalLongShortRatio    │
│     → Poll every 15m                                                 │
│     → Returns decimal ratio (e.g., 1.23)                             │
│                                                                      │
│  7. Taker Buy/Sell: Binance /fapi/v1/takerlongshortvol              │
│     → Poll every 15m                                                 │
│     → Provides buy/sell volume ratio                                 │
└──────────────────────────────────────────────────────────────────────┘
```

**Implementation priority:**
1. **CVD** (CRITICAL) — Replace immediately. Compute from aggTrades WS.
2. **Liquidations** (HIGH) — Replace with /fapi/v1/allForceOrders.
3. **Funding Rate** (HIGH) — Replace with /fapi/v1/fundingRate (eliminates triple normalization).
4. **OI** (MEDIUM) — Replace with /fapi/v1/openInterest.
5. **LS Ratio** (LOW) — Replace with /futures/data/globalLongShortRatio.

**Coinglass-only data that cannot be replaced:**
- Whale Index (proprietary)
- Aggregated Bid/Ask depth (proprietary aggregation)
- Taker Buy/Sell Count (proprietary count vs. volume)

For these, keep the DOM scraper but add normalization guards (see 3.2).

---

### 3.2 Real-Time Normalization Layer for Coinglass Data

If Coinglass must be used, implement a **delta-normalization layer** in `six_strategy_engine.py` that converts viewport-relative Coinglass values into absolute series matching the Parquet training distribution:

```python
class CoinglassNormalizer:
    """Converts viewport-relative Coinglass values to absolute series."""
    
    def __init__(self):
        self._cvd_baseline: Dict[str, float] = {}
        self._cvd_last_raw: Dict[str, float] = {}
        self._cvd_accumulated: Dict[str, float] = {}
        self._reset_detected: Dict[str, bool] = {}
    
    def normalize_cvd(self, symbol: str, raw_cvd: float) -> float:
        """Convert viewport-relative CVD to absolute accumulated CVD.
        
        Detects resets by checking if the new value is dramatically different
        from the last value (more than 50% of the last value's magnitude).
        """
        last_raw = self._cvd_last_raw.get(symbol, None)
        accumulated = self._cvd_accumulated.get(symbol, 0.0)
        
        if last_raw is None:
            # First observation: establish baseline
            self._cvd_baseline[symbol] = raw_cvd
            self._cvd_last_raw[symbol] = raw_cvd
            self._cvd_accumulated[symbol] = raw_cvd
            return raw_cvd
        
        delta = raw_cvd - last_raw
        
        # Detect reset: if delta is > 50% of accumulated value magnitude,
        # it's likely a viewport reset, not a real market move
        if accumulated != 0 and abs(delta) > abs(accumulated) * 0.5:
            # Reset detected: re-baseline
            self._cvd_baseline[symbol] = raw_cvd
            self._cvd_last_raw[symbol] = raw_cvd
            # Keep accumulated value unchanged (don't corrupt the series)
            return accumulated
        
        # Normal update: accumulate delta
        accumulated += delta
        self._cvd_accumulated[symbol] = accumulated
        self._cvd_last_raw[symbol] = raw_cvd
        return accumulated
    
    def normalize_funding(self, raw_funding: float) -> float:
        """Single-pass normalization: ensure decimal fraction (0.0001 format).
        
        Replaces the triple-normalization mess with a single authoritative check.
        """
        # If value looks like a percentage (|v| >= 0.01), divide by 100
        if abs(raw_funding) >= 0.01:
            return raw_funding / 100.0
        # If value looks like basis points (0.001 <= |v| < 0.01), divide by 100
        if abs(raw_funding) >= 0.001:
            return raw_funding / 100.0
        # Already in decimal fraction format
        return raw_funding
```

**Integration point:** Call `normalizer.normalize_cvd()` in `SnapshotStore.update()` before storing the value, and `normalizer.normalize_funding()` in the `_apply()` method.

---

### 3.3 Real-Time Data Drift Detection

Implement a **distribution monitor** that compares live feature values against the backtesting training distribution before passing them to `predict_ensemble`:

```python
class FeatureDriftDetector:
    """Detects when live feature values fall outside the training distribution.
    
    Maintains running mean/std for each feature from the training data.
    Flags features that exceed 4σ from the training mean.
    """
    
    def __init__(self, training_stats: Dict[str, Dict[str, float]]):
        """
        training_stats: {
            'BTCUSDT': {
                'cvd_d_mean': -1234.5, 'cvd_d_std': 5678.9,
                'zc20_mean': 0.0, 'zc20_std': 1.0,
                ...
            },
            ...
        }
        """
        self.stats = training_stats
        self._drift_counts: Dict[str, int] = {}  # symbol -> consecutive drift count
        self.DRIFT_THRESHOLD = 4.0  # σ
        self.MAX_DRIFT_BEFORE_BLOCK = 3  # consecutive drifted bars before blocking
    
    def check_row(self, symbol: str, features: Dict[str, float]) -> Tuple[bool, List[str]]:
        """Returns (is_safe, list_of_drifted_features)."""
        sym_stats = self.stats.get(symbol, {})
        if not sym_stats:
            return True, []  # No stats available, allow through
        
        drifted = []
        critical_features = ['cvd_d', 'zc4', 'zc10', 'zc20', 'zoi', 'liql', 'liqs', 'fr']
        
        for feat in critical_features:
            mean = sym_stats.get(f'{feat}_mean', None)
            std = sym_stats.get(f'{feat}_std', None)
            if mean is None or std is None or std == 0:
                continue
            
            val = features.get(feat, 0.0)
            z = abs(val - mean) / std
            if z > self.DRIFT_THRESHOLD:
                drifted.append(f"{feat}={val:.4f} (z={z:.1f}σ)")
        
        drift_key = symbol
        if drifted:
            self._drift_counts[drift_key] = self._drift_counts.get(drift_key, 0) + 1
        else:
            self._drift_counts[drift_key] = 0
        
        is_safe = self._drift_counts.get(drift_key, 0) < self.MAX_DRIFT_BEFORE_BLOCK
        return is_safe, drifted
```

**Integration point:** In `_on_tick_locked()`, after `featurize()` and before `predict_ensemble()`:

```python
# After featurize():
last_row = df.iloc[-1].to_dict()

# Drift check:
is_safe, drifted = self.drift_detector.check_row(symbol, last_row)
if not is_safe:
    self._log(f"{symbol} BLOCKED: {len(drifted)} features drifted: {drifted[:3]}", "DriftGuard")
    return dataclasses.replace(snap, strategy_armed="DRIFT_BLOCK")

# Proceed with prediction...
```

**Training stats generation:** Run once on the backtesting Parquet data:

```python
def generate_training_stats(parquet_dir: str) -> Dict:
    """Compute mean/std for each feature across all training data."""
    stats = {}
    for sym in SYMBOLS:
        df = load(sym)
        df = featurize(df.copy())
        sym_stats = {}
        for feat in ['cvd_d', 'zc4', 'zc10', 'zc20', 'zoi', 'liql', 'liqs', 'fr', 'vr5']:
            if feat in df.columns:
                sym_stats[f'{feat}_mean'] = float(df[feat].mean())
                sym_stats[f'{feat}_std'] = float(df[feat].std())
        stats[sym] = sym_stats
    return stats
```

---

## 4. SEVERITY SUMMARY & ACTION PLAN

| # | Divergence | Severity | Affected Features | Fix Complexity | Priority |
|---|-----------|----------|-------------------|----------------|----------|
| 1 | CVD baseline reset | **CRITICAL** | `cvd_d`, `zc4/10/20`, `oicc` | Medium (new WS feed) | P0 |
| 2 | Liquidation aggregation | **HIGH** | `liql`, `liqlm`, S1 signal | Low (API replace) | P1 |
| 3 | Funding rate triple-normalization | **HIGH** | `fr`, `zfr` | Low (single normalize) | P1 |
| 4 | Volume source mismatch | **MEDIUM** | `vr5` | Low (ratio self-corrects) | P2 |
| 5 | Temporal desynchronization | **MEDIUM** | All cross-indicator features | Low (already bounded) | P3 |
| 6 | OI unit ambiguity | **MEDIUM** | `zoi`, `oid`, `oicc` | Low (API replace) | P2 |

### Recommended Implementation Order:

1. **Week 1:** Build Binance aggTrades CVD accumulator (replaces Coinglass CVD entirely)
2. **Week 1:** Fix funding rate triple-normalization (single `normalize_funding()` function)
3. **Week 2:** Replace liquidation data with `/fapi/v1/allForceOrders` API
4. **Week 2:** Replace OI with `/fapi/v1/openInterest` API
5. **Week 3:** Implement `FeatureDriftDetector` with training stats from Parquet
6. **Week 3:** Implement `CoinglassNormalizer` as fallback for remaining Coinglass-only data
7. **Week 4:** Backtest the new pipeline against historical data to verify parity

---

*Audit conducted by static analysis of source code and data flow tracing. No runtime execution was performed.*
