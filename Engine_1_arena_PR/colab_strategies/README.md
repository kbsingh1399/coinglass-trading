# OOS Backtesting Suite — Folder Structure

## ✅ Primary Runner (Verified Results)

**`run_all_6.py`** — This is the file that produced `all_6_results.json` with **118/120 windows PASS**.

### How to Reproduce the Verified Results

```bash
python colab_strategies/run_all_6.py
```

This will:
1. Run all 6 strategies across 20 walk-forward windows (2020-03 to 2026-07)
2. Use fixed parameters: TP=5.0R, Trail=0.8ATR, MINTR=6, TDD=30%
3. Output results to `all_6_results.json`

### Requirements
- Full 6-year dataset (2020-03 to 2026-07) in `backtesting_data/` or `G:\My Drive\_Trading_Data\15m\parquet`
- Python packages: pandas, numpy, lightgbm, xgboost, numba, scikit-learn, pyarrow

### Strategy List
1. **S1_Liquidation** — Trend pullback + abnormal liquidation spike
2. **S2_CVD_Momentum** — Tight trend pullback on strong CVD moves
3. **S3_Trend_Follow** — Classic macro trend (EMA 200/800 crossover)
4. **S4_Mean_Reversion** — RSI extremes with deep pullback
5. **S5_Vol_Breakout** — Trend pullback + elevated volatility + CVD
6. **S6_OI_Coherence** — Trend pullback + OI/CVD directional agreement

### Pass Criteria
- Win Rate > 40%
- ROI ≥ 20%
- Max Drawdown < 30%
- Min 6 trades per window

---

## 📁 Folder Structure

```
colab_strategies/
├── run_all_6.py                  ← PRIMARY: Verified runner (produces all_6_results.json)
├── run_all_6_patched.py          ← Patched variant (for testing)
├── all_6_results.json            ← Verified results: 118/120 PASS
├── patched_results.json          ← Patched results (for comparison)
├── monthly_pnl.py                ← Monthly PnL analysis utility
├── prep_run_all.py               ← Data preparation script
├── README.md                     ← This file
│
├── optuna_variants/              ← Legacy Optuna-based implementations
│   ├── opt_s1_colab_standalone.py
│   ├── opt_s2_colab_standalone.py
│   ├── opt_s3_colab_standalone.py
│   ├── opt_s4_colab_standalone.py
│   ├── opt_s5_colab_standalone.py
│   └── opt_s6_colab_standalone.py
│
└── colab_strategies/             ← Original archive (untouched)
    ├── run_all_6.py
    ├── all_6_results.json
    ├── opt_s*_colab_standalone.py
    └── ... (19 files total)
```

---

## ⚠️ Important: Different Implementations

The files in `optuna_variants/` are **NOT** the same as `run_all_6.py`:

| Feature | `run_all_6.py` (verified) | `optuna_variants/opt_s*.py` |
|---|---|---|
| Signal logic | Inline `make_signal_s1`–`s6` | Complex per-file Optuna logic |
| TP/Trail | Fixed: 5.0R / 0.8ATR | Searches: [5,7,10] × [0.4–2.0] |
| Min trades | 6 | 8 |
| Max DD | 30% | 15% |
| ML pipeline | LGB+XGB ensemble, feature importance | 50 Optuna trials, Kelly sizing |
| Results | 118/120 PASS | Different (often FAIL) |

**To reproduce the verified results, always use `run_all_6.py`.**

---

## 📊 Verified Results Summary

| Strategy | Windows | PASS | FAIL | UNDETERMINED | Net PnL | WR% | PF |
|---|---|---|---|---|---|---|---|
| S1_Liquidation | 20 | 18 | 0 | 2 | $55,399 | 74.2% | 5.34 |
| S2_CVD_Momentum | 20 | 20 | 0 | 0 | $65,225 | 76.6% | 5.96 |
| S3_Trend_Follow | 20 | 20 | 0 | 0 | $62,329 | 75.9% | 5.95 |
| S4_Mean_Reversion | 20 | 20 | 0 | 0 | $73,827 | 77.1% | 5.90 |
| S5_Vol_Breakout | 20 | 20 | 0 | 0 | $63,115 | 79.0% | 6.18 |
| S6_OI_Coherence | 20 | 20 | 0 | 0 | $61,646 | 75.9% | 5.75 |
| **COMBINED** | **120** | **118** | **0** | **2** | **$381,541** | **76.5%** | **5.85** |

---

## 🔧 Troubleshooting

### "No valid trades found" in early windows
- **Cause**: Parquet data doesn't cover 2020-2023
- **Solution**: Use full 6-year dataset from `G:\My Drive\_Trading_Data\15m\parquet`

### Different results than `all_6_results.json`
- **Cause**: Running `optuna_variants/opt_s*.py` instead of `run_all_6.py`
- **Solution**: Always use `python colab_strategies/run_all_6.py`

### ModuleNotFoundError: pyarrow
- **Solution**: `pip install pyarrow`
