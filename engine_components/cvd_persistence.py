"""
CVD Accumulator Persistence
============================
Saves and restores CoinglassNormalizer state to disk on shutdown/startup.
Prevents massive false cvd_d spikes on the first bar after engine restart.

Integration into Engine_1.py:
    1. Add to CoinglassNormalizer.__init__():
       self._state_file = os.path.join(base_dir, "live_data", "cvd_normalizer_state.json")
       self._load_state()
    
    2. Add save_state() and _load_state() methods (below)
    
    3. In the shutdown handler (sig_handler or finally block):
       store.normalizer.save_state()
"""
import os
import json
import time
from typing import Dict


class CVDStateMixin:
    """Mixin that adds save/load state to CoinglassNormalizer.
    
    Add this as a base class:
        class CoinglassNormalizer(CVDStateMixin):
    """
    
    _STATE_FILE = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 
        "live_data", "cvd_normalizer_state.json"
    )
    
    def save_state(self) -> None:
        """Persist CVD accumulator state to disk.
        
        Called on engine shutdown to prevent cvd_d spike on restart.
        The state file contains the accumulated CVD values and last raw
        values for each symbol, allowing the normalizer to resume
        delta-accumulation seamlessly.
        """
        state = {
            "timestamp": time.time(),
            "cvd_accumulated": dict(getattr(self, '_cvd_accumulated', {})),
            "cvd_last_raw": dict(getattr(self, '_cvd_last_raw', {})),
            "cvd_baseline": dict(getattr(self, '_cvd_baseline', {})),
            "spot_cvd_accumulated": dict(getattr(self, '_spot_cvd_accumulated', {})),
            "spot_cvd_last_raw": dict(getattr(self, '_spot_cvd_last_raw', {})),
            "spot_cvd_baseline": dict(getattr(self, '_spot_cvd_baseline', {})),
        }
        try:
            os.makedirs(os.path.dirname(self._STATE_FILE), exist_ok=True)
            tmp = self._STATE_FILE + ".tmp"
            with open(tmp, 'w') as f:
                json.dump(state, f, indent=2)
            os.replace(tmp, self._STATE_FILE)
            n_syms = len(state["cvd_accumulated"])
            print(f"[CVD] State saved: {n_syms} symbols to {self._STATE_FILE}")
        except Exception as e:
            print(f"[CVD] Failed to save state: {e}")
    
    def _load_state(self, max_age_hours: float = 4.0) -> None:
        """Restore CVD accumulator state from disk.
        
        Args:
            max_age_hours: Maximum age of state file in hours. Older files
                are ignored to prevent stale baselines from corrupting live data.
                Default 4h covers typical restart windows.
        """
        if not os.path.exists(self._STATE_FILE):
            print("[CVD] No saved state found — starting fresh")
            return
        
        try:
            with open(self._STATE_FILE, 'r') as f:
                state = json.load(f)
            
            # Check age
            saved_ts = state.get("timestamp", 0)
            age_hours = (time.time() - saved_ts) / 3600.0
            if age_hours > max_age_hours:
                print(f"[CVD] Saved state is {age_hours:.1f}h old (max {max_age_hours}h) — discarding")
                return
            
            # Restore state
            self._cvd_accumulated = state.get("cvd_accumulated", {})
            self._cvd_last_raw = state.get("cvd_last_raw", {})
            self._cvd_baseline = state.get("cvd_baseline", {})
            self._spot_cvd_accumulated = state.get("spot_cvd_accumulated", {})
            self._spot_cvd_last_raw = state.get("spot_cvd_last_raw", {})
            self._spot_cvd_baseline = state.get("spot_cvd_baseline", {})
            
            n_syms = len(self._cvd_accumulated)
            print(f"[CVD] State restored: {n_syms} symbols (age: {age_hours:.1f}h)")
            
        except Exception as e:
            print(f"[CVD] Failed to load state: {e}")


# ─── Integration Code for Engine_1.py ────────────────────────────────
# 
# 1. Modify CoinglassNormalizer class definition:
#
#    class CoinglassNormalizer(CVDStateMixin):
#        """Converts viewport-relative Coinglass values to absolute series."""
#        
#        def __init__(self):
#            self._cvd_baseline: Dict[str, float] = {}
#            self._cvd_last_raw: Dict[str, float] = {}
#            self._cvd_accumulated: Dict[str, float] = {}
#            self._spot_cvd_baseline: Dict[str, float] = {}
#            self._spot_cvd_last_raw: Dict[str, float] = {}
#            self._spot_cvd_accumulated: Dict[str, float] = {}
#            self._load_state()  # ← ADD THIS LINE
#
# 2. Add import at top of Engine_1.py:
#
#    from engine_components.cvd_persistence import CVDStateMixin
#
# 3. In the shutdown handler (sig_handler or finally block of main()):
#
#    # Save CVD normalizer state before exit
#    if hasattr(store, 'normalizer'):
#        store.normalizer.save_state()
#
# ─────────────────────────────────────────────────────────────────────
