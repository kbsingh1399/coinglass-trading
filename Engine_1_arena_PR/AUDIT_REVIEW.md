# Engine_1_arena_PR — Strategy Review & Risk Analysis

**Date:** 2026-08-18
**Files Reviewed:** `run_all_6.py`, `six_strategy_engine.py`
**Branch:** `arena/019fec7a-coinglass-trading`

---

## 1. HIDDEN EDGE-CASE RISKS & LOOK-AHEAD BIASES IN `run_all_6.py`

### 1.1 S2/S3 Signal Subset Collision (HIGH)

**S2** fires at `p8 < -0.20`. **S3** fires at `p8 < -0.10`. Every S2 signal is automatically an S3 signal. In the backtest, both strategies run independently, so the same trade appears in both S2 and S3 results, inflating the aggregate PnL when strategies are combined.

In live trading, `six_strategy_engine.py` iterates all 6 strategies per bar. When S2 fires, S3 fires on the same bar for the same symbol. The `has_active` check prevents duplicate entries within the same strategy, but NOT across strategies. Result: S2 and S3 both enter the same trade, doubling exposure on the strongest pullbacks.

**Fix:** Add an exclusion guard in S3:
```python
def make_signal_s3(df):
    mc = df.get("mc", pd.Series(0, index=df.index)).values
    p8 = df.get("p8", pd.Series(0, index=df.index)).values
    # Exclude S2's deeper pullback zone to prevent double-entry
    out = np.zeros(len(df), dtype=np.int32)
    out[(mc > 0) & (p8 < -0.10) & (p8 >= -0.20)] = 1
    out[(mc < 0) & (p8 > 0.10) & (p8 <= 0.20)] = -1
    return out
```

### 1.2 EMA-800 Warmup Look-Ahead (MEDIUM)

`featurize()` computes `df["es"] = df["Close"].ewm(span=800, min_periods=100).mean()`. The `min_periods=100` means the EMA-800 is computed from bar 100 onward, but it doesn't stabilize until ~2400 bars (3× span). The macro signal `mc` derived from it is unreliable for the first ~200 bars of each dataset.

`gen_trades_numba` starts scanning at `i=200`, which is before the EMA-800 has converged. Signals in bars 200-800 may fire on a macro signal that would be different if computed with full historical context.

**Fix:** Increase the scan start from `i=200` to `i=800`:
```python
@njit(fastmath=True, nogil=True)
def gen_trades_numba(h, l, c, o, a, sig):
    n = len(c); results = []; i = 800; cd = 0  # Was 200
```

### 1.3 Walk-Forward Threshold Overfitting (MEDIUM)

`best_thresh()` sweeps `np.arange(0.50, 0.92, 0.02)` (21 threshold values) on the validation set, then applies the best one to the test set. With only `MINTR=6` minimum trades in validation, the threshold selection is fitting to noise. A validation set with 8 trades where 6 win at threshold 0.72 and 4 win at 0.55 will select 0.72, but this is statistically meaningless with N=8.

**Fix:** Require a minimum of 20 validation trades for threshold optimization. Below that, use the default 0.55:
```python
def best_thresh(pdf):
    if len(pdf) < 20:
        return 0.55
    # ... existing sweep logic ...
```

### 1.4 Cooldown Too Short for 15m Bars (LOW)

`cd = i + bh + 2` gives a 2-bar (30-minute) cooldown after trade exit. In a trending market, the same signal can re-fire 30 minutes after an SL exit, potentially entering into the same adverse move.

**Fix:** Use the same cooldown as the live engine's `REENTRY_COOLDOWN_SL_SECS = 1800` (30 min = 2 bars at 15m). This is already correct, but consider increasing to 4 bars (1 hour) for SL exits specifically:
```python
# In gen_trades_numba, track exit reason:
if l[j] <= cs:  # SL hit
    cd = i + bh + 4  # 4-bar cooldown after SL
else:
    cd = i + bh + 2  # 2-bar cooldown after TP/timeout
```

### 1.5 Performance Bottleneck: Per-Symbol Full featurize() (LOW)

`run_one()` calls `featurize(df.copy(), ref)` for each of 14 symbols. The BTC reference DataFrame is joined and computed fresh each time. With 20 walk-forward windows × 14 symbols × ~800 bars of feature computation, this is O(224,000) rolling window operations.

**Fix:** Pre-compute the BTC reference features once and pass the pre-computed columns:
```python
btc_ref = featurize(btc_df.copy())  # Compute once
btc_features = btc_ref[["Close", "CVD", "mc", "ef", "es"]].copy()
btc_features.columns = ["btc_" + c for c in btc_features.columns]
# Pass btc_features to all symbol featurize() calls
```

---

## 2. DEEP PURE TREND (S2/S3) — MARKET-CONTEXT FILTER RECOMMENDATIONS

### 2.1 Current State

Both S2 and S3 rely exclusively on two conditions: `mc != 0` (macro trend) and `p8` (pullback depth). This is elegant but vulnerable to:

- **Ranging markets:** The EMA-200/800 crossover (`mc`) is a lagging indicator. After a trend reversal, `mc` can remain positive for 50-100 bars while price chops sideways. S2/S3 will fire on every pullback in a dead trend.
- **Liquidity vacuums:** Deep pullbacks (`p8 < -0.20`) often coincide with low liquidity. The entry fills at a bad price, and the SL (1 ATR) is too tight for the actual volatility.

### 2.2 Recommended Filters (Without Overfitting)

**Filter A: EMA Slope Confirmation (Strongest Recommendation)**

The macro signal `mc` tells you the trend *direction* but not the trend *strength*. Add a slope check on the EMA-200:

```python
def make_signal_s2(df):
    mc = df.get("mc", pd.Series(0, index=df.index)).values
    p8 = df.get("p8", pd.Series(0, index=df.index)).values
    ef = df.get("ef", pd.Series(0, index=df.index)).values  # EMA-200
    
    # EMA-200 slope: current vs 10 bars ago, normalized by ATR
    atr = df.get("atr", pd.Series(1, index=df.index)).values
    ef_slope = np.zeros(len(df))
    ef_slope[10:] = (ef[10:] - ef[:-10]) / np.maximum(atr[10:], 1e-10)
    
    out = np.zeros(len(df), dtype=np.int32)
    # Require EMA-200 slope > 0.5 ATR over 10 bars (trend is accelerating)
    out[(mc > 0) & (p8 < -0.20) & (ef_slope > 0.5)] = 1
    out[(mc < 0) & (p8 > 0.20) & (ef_slope < -0.5)] = -1
    return out
```

**Why this works:** A deep pullback in an accelerating trend is a buying opportunity. A deep pullback in a flat/decaying trend is a reversal signal. The slope filter eliminates the latter without adding new parameters (it reuses `ef` and `atr`).

**Filter B: Volume Ratio Floor (Secondary Recommendation)**

Deep pullbacks on declining volume are often exhaustion moves, not trend continuations. Add a volume ratio check:

```python
vr5 = df.get("vr5", pd.Series(1.0, index=df.index)).values
# Require volume > 50% of 20-bar average (not a dead market)
out[(mc > 0) & (p8 < -0.20) & (vr5 > 0.5)] = 1
```

**Why this is safe:** `vr5` is already computed in `featurize()`. The 0.5 threshold is conservative (only blocks entries during extreme volume droughts). It won't overfit because volume droughts are genuinely bad entry conditions.

**Filter C: RSI Non-Extreme Guard (Tertiary)**

S2/S3 currently have no RSI filter. A deep pullback with RSI < 20 is likely capitulation, not a pullback. Add a floor:

```python
rsi = df.get("rsi", pd.Series(50, index=df.index)).values
# Block entries when RSI < 25 (capitulation) or > 75 (euphoria)
out[(mc > 0) & (p8 < -0.20) & (rsi > 25) & (rsi < 75)] = 1
```

**Why this is safe:** S5 already uses `25 < rsi < 75` for its bonus path. Applying it to S2/S3 is consistent and prevents entries during extreme sentiment.

### 2.3 Filters NOT Recommended

- **ADX:** Requires a new feature computation (not in `featurize()`). Adds complexity without clear edge over EMA slope.
- **Bollinger Band width:** Redundant with `vr` (volatility regime z-score).
- **Order book imbalance:** Not available in the backtest data pipeline. Would create a backtest/live divergence.

---

## 3. ADAPTIVE FILTERING (`_consec_losses`) — IMPROVEMENTS

### 3.1 Critical Bug: `_thresh_lift` Is Computed But Never Applied

In `notify_trade_closed()`, the code updates `self._thresh_lift[symbol]` on every loss/win. But in `_on_tick_locked()`, the threshold check uses:

```python
base_thresh = self.thresholds[strat_key].get(symbol, 0.55)
if float(prob) < (float(base_thresh) - 1e-5):
    continue
```

The `_thresh_lift` value is **never added to `base_thresh`**. The adaptive threshold mechanism is dead code.

**Fix:**
```python
base_thresh = self.thresholds[strat_key].get(symbol, 0.55)
adaptive_thresh = base_thresh + self._thresh_lift.get(symbol, 0.0)
if float(prob) < (float(adaptive_thresh) - 1e-5):
    continue
```

### 3.2 Suspension Bar Index Is Unstable

```python
current_bar = len(self.candles_history.get(symbol, []))
self._dir_suspend_until[loss_key] = current_bar + 3
```

`len(self.candles_history)` is the number of historical candles, which grows as new candles arrive. If the history deque has `maxlen=1200`, the length caps at 1200. When a new candle is appended and an old one is evicted, the length stays at 1200, but the "current bar" index should have advanced by 1.

**Fix:** Use a monotonically increasing bar counter:
```python
# In __init__:
self._bar_counter: Dict[str, int] = {s: 0 for s in symbols}

# In _on_tick_locked, on candle rollover:
self._bar_counter[symbol] = self._bar_counter.get(symbol, 0) + 1

# In notify_trade_closed:
current_bar = self._bar_counter.get(symbol, 0)
self._dir_suspend_until[loss_key] = current_bar + 3

# In _on_tick_locked, when checking suspension:
current_bar = self._bar_counter.get(symbol, 0)
if self._dir_suspend_until.get(suspend_key, 0) > current_bar:
    ...
```

### 3.3 Smoother Drawdown Recovery

The current recovery logic is binary: win → reset everything. This is too aggressive. A single win after 3 losses shouldn't fully restore confidence. Implement exponential decay:

```python
def notify_trade_closed(self, trade: dict) -> None:
    # ... existing loss logic ...
    
    if is_loss:
        # Existing: increment, raise lift
        pass
    else:
        # IMPROVED: Gradual recovery instead of full reset
        self._consec_losses[loss_key] = max(0, self._consec_losses[loss_key] - 1)  # Decrement, not zero
        old_lift = self._thresh_lift.get(symbol, 0.0)
        # Decay lift by 25% per win (not flat 0.05)
        self._thresh_lift[symbol] = old_lift * 0.75
        if self._thresh_lift[symbol] < 0.01:
            self._thresh_lift[symbol] = 0.0
            self._consec_losses[loss_key] = 0  # Full reset only when lift is negligible
```

**Why this is better:** After 3 consecutive losses (lift = 0.15), a single win reduces lift to 0.1125 (not 0.10). A second win reduces to 0.084. A third win reduces to 0.063. Full recovery takes ~4-5 wins instead of 1, which matches the psychological reality that confidence rebuilds gradually.

### 3.4 Add Strategy-Level Loss Tracking

Currently, losses are tracked per `(symbol, direction)`. But if S1 and S3 both lose on BTCUSDT LONG, only one counter increments (whichever trade closes last). Add strategy-level tracking:

```python
loss_key = (symbol, direction, trade.get('strategy', ''))
```

This prevents a winning S1 trade from resetting the S3 loss counter on the same symbol/direction.

---

## 4. SUMMARY OF RECOMMENDED CHANGES

| # | File | Change | Impact | Priority |
|---|------|--------|--------|----------|
| 1 | `run_all_6.py` | S3 exclude S2 zone (`p8 >= -0.20`) | Prevents double-counting in backtest | HIGH |
| 2 | `run_all_6.py` | Increase scan start from 200 to 800 | Eliminates EMA-800 warmup bias | MEDIUM |
| 3 | `run_all_6.py` | Require 20+ validation trades for threshold sweep | Prevents threshold overfitting | MEDIUM |
| 4 | `six_strategy_engine.py` | Apply `_thresh_lift` to actual threshold check | Activates dead adaptive code | CRITICAL |
| 5 | `six_strategy_engine.py` | Use monotonic `_bar_counter` for suspension | Fixes suspension timing | HIGH |
| 6 | `six_strategy_engine.py` | Exponential decay recovery (0.75× per win) | Smoother drawdown recovery | MEDIUM |
| 7 | Both | Add EMA slope filter to S2/S3 | Reduces false breakouts | RECOMMENDED |
| 8 | Both | Add `vr5 > 0.5` volume floor to S2/S3 | Blocks dead-market entries | RECOMMENDED |
| 9 | Both | Add `25 < rsi < 75` guard to S2/S3 | Blocks capitulation entries | OPTIONAL |
| 10 | `six_strategy_engine.py` | Strategy-level loss tracking | Prevents cross-strategy counter reset | LOW |

---

*Review conducted by static analysis of source code. No runtime backtesting was performed to validate filter recommendations.*
