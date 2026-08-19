"""
Drift Detector Dry-Run Mode
============================
When --dry-run-drift is active, the FeatureDriftDetector logs all 4σ drift
blocks to a JSONL file instead of actually blocking predictions. This allows
calibration of the false positive rate over 24 hours before going live.

Integration into six_strategy_engine.py:
    1. Add `dry_run` parameter to FeatureDriftDetector.__init__()
    2. Modify check_row() to log instead of block when dry_run=True
    3. Add --dry-run-drift CLI flag to Engine_1.py
"""
import os
import json
import time
from typing import Dict, List, Tuple


DRIFT_LOG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "live_data", "drift_dryrun_log.jsonl"
)


def log_drift_event(symbol: str, drifted_features: List[str], 
                    features: Dict[str, float], blocked: bool) -> None:
    """Append a drift event to the JSONL log file.
    
    Each line is a self-contained JSON object with timestamp, symbol,
    drifted features, their z-scores, and whether the prediction was
    actually blocked or just logged (dry-run mode).
    """
    event = {
        "timestamp": time.time(),
        "datetime": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
        "symbol": symbol,
        "blocked": blocked,
        "drifted_features": drifted_features,
        "feature_values": {k: round(v, 6) for k, v in features.items() 
                          if k in ['cvd_d', 'zc4', 'zc10', 'zc20', 'zoi', 'liql', 'liqs', 'fr', 'vr5']},
    }
    try:
        os.makedirs(os.path.dirname(DRIFT_LOG_FILE), exist_ok=True)
        with open(DRIFT_LOG_FILE, 'a') as f:
            f.write(json.dumps(event) + "\n")
    except Exception:
        pass  # Never let logging crash the engine


class DriftDryRunMixin:
    """Mixin that adds dry-run mode to FeatureDriftDetector.
    
    Integration:
        class FeatureDriftDetector(DriftDryRunMixin):
            def __init__(self, training_stats, dry_run=False):
                self.dry_run = dry_run
                ...
    """
    
    def check_row_dryrun(self, symbol: str, features: Dict[str, float]) -> Tuple[bool, List[str]]:
        """Dry-run version of check_row: always returns is_safe=True but logs drifts.
        
        Returns:
            (True, drifted_features) — always allows prediction through,
            but logs the drift event for later analysis.
        """
        sym_stats = self.stats.get(symbol, {})
        if not sym_stats:
            return True, []
        
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
        
        if drifted:
            self._drift_counts[symbol] = self._drift_counts.get(symbol, 0) + 1
            would_block = self._drift_counts.get(symbol, 0) >= self.MAX_DRIFT_BEFORE_BLOCK
            log_drift_event(symbol, drifted, features, blocked=would_block)
        else:
            self._drift_counts[symbol] = 0
        
        # DRY-RUN: Always return True (never block)
        return True, drifted


# ─── Integration Code for six_strategy_engine.py ─────────────────────
#
# 1. Add import at top:
#
#    from engine_components.drift_dryrun import DriftDryRunMixin, log_drift_event
#
# 2. Modify FeatureDriftDetector class:
#
#    class FeatureDriftDetector(DriftDryRunMixin):
#        def __init__(self, training_stats, dry_run=False):
#            self.stats = training_stats
#            self._drift_counts = {}
#            self.DRIFT_THRESHOLD = 4.0
#            self.MAX_DRIFT_BEFORE_BLOCK = 3
#            self.dry_run = dry_run  # ← ADD THIS
#
# 3. Modify check_row to delegate to dry-run when active:
#
#    def check_row(self, symbol, features):
#        if self.dry_run:
#            return self.check_row_dryrun(symbol, features)
#        # ... existing blocking logic ...
#
# 4. In Engine_1.py main(), pass the flag:
#
#    parser.add_argument("--dry-run-drift", action="store_true",
#        help="Log drift blocks instead of blocking predictions (calibration mode)")
#    args = parser.parse_args()
#    
#    predictor = LiveSixStrategyPredictor(ALL_SYMBOLS)
#    predictor.drift_detector.dry_run = args.dry_run_drift
#
# ─────────────────────────────────────────────────────────────────────
#
# ─── Analysis Script ─────────────────────────────────────────────────
#
# After 24 hours of dry-run, analyze the log:
#
#    python -c "
#    import json
#    events = [json.loads(l) for l in open('live_data/drift_dryrun_log.jsonl')]
#    blocked = [e for e in events if e['blocked']]
#    print(f'Total drift events: {len(events)}')
#    print(f'Would-be blocks: {len(blocked)}')
#    print(f'False positive rate: {len(blocked)/max(len(events),1)*100:.1f}%')
#    for sym in set(e['symbol'] for e in blocked):
#        sym_blocks = [e for e in blocked if e['symbol'] == sym]
#        print(f'  {sym}: {len(sym_blocks)} blocks')
#    "
#
# ─────────────────────────────────────────────────────────────────────
