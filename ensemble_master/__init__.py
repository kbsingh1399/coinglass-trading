"""Ensemble Master — 2-of-3 microstructure consensus strategy."""
from pathlib import Path
import json

_CFG = Path(__file__).resolve().parent / "configs" / "default.json"


def load_default_params() -> dict:
    if _CFG.exists():
        return json.loads(_CFG.read_text())
    return {
        "sl_mult": 1.0,
        "tp_mult": 6.0,
        "trail_act": 3.5,
        "trail_buf": 0.45,
        "min_votes": 2,
        "vote_window": 1,
        "vol_regime_min": -1.0,
    }
