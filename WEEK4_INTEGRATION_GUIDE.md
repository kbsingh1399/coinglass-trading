# Week 4 Production Readiness — Integration Guide

**Commit:** `pending`  
**Branch:** `arena/019fec7a-coinglass-trading`  
**Files Added:**
- `test_pipeline_parity.py` — End-to-end parity test script
- `engine_components/cvd_persistence.py` — CVD state save/load mixin
- `engine_components/drift_dryrun.py` — Drift detector dry-run mixin
- `WEEK4_INTEGRATION_GUIDE.md` — This file

---

## Component 1: End-to-End Parity Test

### What It Does
Takes the last 100 rows of Parquet backtesting data, pushes them through the **live** `featurize()` + `predict_ensemble()` pipeline, and asserts output matches backtest within 0.01 margin.

### How to Run
```bash
# Full test (all 14 symbols, 100 rows)
python test_pipeline_parity.py

# Quick test (BTC + ETH only, 50 rows)
python test_pipeline_parity.py --symbols BTCUSDT,ETHUSDT --rows 50

# Strict tolerance (0.005 margin)
python test_pipeline_parity.py --tolerance 0.005

# Custom paths
python test_pipeline_parity.py --data-dir /path/to/Backtesting_Data --models-dir /path/to/six_strategy_models
```

### Exit Codes
- `0` = ALL PASS — pipeline is ready for live trading
- `1` = FAIL — divergence detected, do NOT go live
- `2` = ERROR — missing data or models

### What It Checks
1. **Signal Parity:** Does `make_signal_s1..s6()` produce the same direction (+1/-1/0) on the same data?
2. **Probability Parity:** Does `predict_ensemble()` produce the same probability (within tolerance)?
3. **Feature Parity:** Implicitly verified — if features diverge, signals and probabilities will too.

---

## Component 2: CVD Accumulator Persistence

### What It Does
Saves `_cvd_accumulated`, `_cvd_last_raw`, and `_cvd_baseline` dicts to `live_data/cvd_normalizer_state.json` on shutdown. Reloads on startup if file is < 4 hours old.

### Integration Steps

**Step 1:** Add import to `Engine_1.py` (near top, after other engine_components imports):
```python
from engine_components.cvd_persistence import CVDStateMixin
```

**Step 2:** Modify `CoinglassNormalizer` class to inherit from mixin:
```python
class CoinglassNormalizer(CVDStateMixin):
    """Converts viewport-relative Coinglass values to absolute series."""
    
    def __init__(self):
        self._cvd_baseline: Dict[str, float] = {}
        self._cvd_last_raw: Dict[str, float] = {}
        self._cvd_accumulated: Dict[str, float] = {}
        self._spot_cvd_baseline: Dict[str, float] = {}
        self._spot_cvd_last_raw: Dict[str, float] = {}
        self._spot_cvd_accumulated: Dict[str, float] = {}
        self._load_state()  # ← ADD THIS LINE at the end of __init__
```

**Step 3:** Add `save_state()` call to shutdown handler. In `main()`, find the `finally` block or `sig_handler`:
```python
# In the shutdown/finally block:
if hasattr(store, 'normalizer'):
    store.normalizer.save_state()
    print("[Shutdown] CVD normalizer state saved.")
```

### Verification
After restart, check logs for:
```
[CVD] State restored: 14 symbols (age: 0.2h)
```
If the first bar after restart shows a massive `cvd_d` spike, the state file is either missing or too old.

---

## Component 3: Drift Detector Dry-Run Mode

### What It Does
When `--dry-run-drift` is active, the `FeatureDriftDetector` logs all 4σ drift events to `live_data/drift_dryrun_log.jsonl` instead of blocking predictions. This lets you calibrate the false positive rate over 24 hours.

### Integration Steps

**Step 1:** Add import to `six_strategy_engine.py` (near top):
```python
from engine_components.drift_dryrun import DriftDryRunMixin, log_drift_event
```

**Step 2:** Modify `FeatureDriftDetector` class:
```python
class FeatureDriftDetector(DriftDryRunMixin):
    def __init__(self, training_stats: Dict[str, Dict[str, float]], dry_run: bool = False):
        self.stats = training_stats
        self._drift_counts: Dict[str, int] = {}
        self.DRIFT_THRESHOLD = 4.0
        self.MAX_DRIFT_BEFORE_BLOCK = 3
        self.dry_run = dry_run  # ← ADD THIS
    
    def check_row(self, symbol: str, features: Dict[str, float]) -> Tuple[bool, List[str]]:
        if self.dry_run:
            return self.check_row_dryrun(symbol, features)  # ← ADD THIS
        # ... existing blocking logic unchanged below ...
```

**Step 3:** Add CLI flag to `Engine_1.py` `main()`:
```python
parser.add_argument("--dry-run-drift", action="store_true",
    help="Log drift blocks instead of blocking (24h calibration mode)")
args = parser.parse_args()

# After predictor initialization:
if args.dry_run_drift:
    predictor.drift_detector.dry_run = True
    print("[DRIFT] Dry-run mode ACTIVE — drift blocks will be logged, not enforced")
```

### How to Analyze After 24 Hours
```bash
# Quick summary
python -c "
import json
events = [json.loads(l) for l in open('live_data/drift_dryrun_log.jsonl')]
blocked = [e for e in events if e['blocked']]
print(f'Total drift events: {len(events)}')
print(f'Would-be blocks: {len(blocked)}')
for sym in set(e['symbol'] for e in blocked):
    sym_blocks = [e for e in blocked if e['symbol'] == sym]
    print(f'  {sym}: {len(sym_blocks)} blocks')
    top_feats = {}
    for e in sym_blocks:
        for f in e['drifted_features']:
            feat_name = f.split('=')[0]
            top_feats[feat_name] = top_feats.get(feat_name, 0) + 1
    for feat, count in sorted(top_feats.items(), key=lambda x: -x[1])[:3]:
        print(f'    {feat}: {count} times')
"
```

### Tuning Guide
- **>50 blocks/24h:** Threshold too aggressive. Increase `DRIFT_THRESHOLD` from 4.0 to 5.0.
- **10-50 blocks/24h:** Acceptable range. Check if blocks cluster around specific symbols (indicates data pipeline issue, not false positive).
- **<10 blocks/24h:** Safe to disable dry-run and enable real blocking.

---

## Pre-Launch Checklist

```
□ 1. Parity test passes (exit code 0) on all 14 symbols
□ 2. CVD persistence saves/restores correctly (verify log output)
□ 3. Drift dry-run runs for 24h with <50 would-be blocks
□ 4. No SIGNAL_DIVERGENCE failures in parity test
□ 5. Max probability divergence < 0.01
□ 6. All 84 models loaded successfully
□ 7. BinanceOIFeed returns USD-converted values (check snapshot debug JSON)
□ 8. forceOrder accumulator resets per-symbol (check liq_long/short in terminal)
□ 9. DOM scraper no longer overwrites OI/liquidation fields
□ 10. Funding rate values in 0.0001-0.001 range (not 0.000001)
```

---

## File Structure After Integration

```
coinglass-trading/
├── Engine_1.py                          # Modified: CVDStateMixin import, shutdown save
├── six_strategy_engine.py               # Modified: DriftDryRunMixin, dry_run flag
├── test_pipeline_parity.py              # NEW: Parity test script
├── engine_components/
│   ├── cvd_persistence.py               # NEW: CVD state save/load mixin
│   ├── drift_dryrun.py                  # NEW: Drift dry-run mixin
│   ├── binance_broker.py
│   └── coinglass_scraper.py
├── live_data/
│   ├── cvd_normalizer_state.json        # Auto-generated by CVD persistence
│   └── drift_dryrun_log.jsonl           # Auto-generated by drift dry-run
├── backtesting_data/                    # Parquet files (required for parity test)
└── six_strategy_models/                 # Trained models (required for parity test)
```
