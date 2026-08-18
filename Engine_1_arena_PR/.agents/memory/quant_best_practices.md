# Quantitative & ML Best Practices

Based on our intensive expanding walk-forward tests and optimizer builds, we have locked in the following core best practices for this trading engine:

## 1. Overcoming Execution Friction (Fee Bleed)
- **The Problem:** 0.10% roundtrip fees and slippage will drain a high-frequency strategy if the profit margins per trade are too thin.
- **Best Practice:** Always enforce a **minimum distance threshold** (e.g., `dist_pct > 0.0035` or 0.35%) from the mean reversion target (like VWAP). Never take trades that are too close to the mean, regardless of what other indicators say.
- **Filter Synergy:** Combine statistical bands (like Z-score or VWAP 2.2 SD) with momentum exhaustion (RSI < 30 or RSI > 70) to filter out weak signals and guarantee you're catching the true rubber-band snap.

## 2. Dynamic Target Exits vs. Static ATR
- **The Problem:** Static ATR trailing stops can give back too much profit during choppy reversion trades. 
- **Best Practice:** Use **Dynamic Exits** (e.g., exiting a VWAP reversion exactly when the price touches the VWAP mean line) rather than strictly waiting for a fixed 5R limit or a trailing stop. This drastically increases Win Rate and locks in profits before the trend reverses again.

## 3. System Memory Constraints & ML OOM Crashes
- **The Problem:** Running multi-threaded Optuna alongside parallelized ML models (LightGBM `n_jobs=-1`) on 14 assets simultaneously will spike RAM usage and trigger fatal Out-Of-Memory (OOM) access violations in C-level libraries.
- **Best Practice:** 
    1. **Strict Garbage Collection**: Never hold base trade dataframes in memory if they aren't actively being optimized. Use generators where possible.
    2. **Smart Checkpointing**: ALWAYS save optimization results to cache (`oos_cache_{strategy}.json`) at the end of *every single window*. This allows the engine to instantly resume from a crash rather than losing days of compute time.

## 4. OOS Walk-Forward Rigor
- **The Problem:** Curve-fitting is the silent killer of ML models.
- **Best Practice:** Maintain strict zero-lookahead bias. Hyperparameters and strategy thresholds must be tuned *strictly* on data prior to the 1-month test window. Do not let Optuna "peek" at the test window.
