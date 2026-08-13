import os
import sys
import dataclasses

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

@dataclasses.dataclass
class StrategyConfig:
    tp_mult: float = 5.0
    trail_atr: float = 0.8
    risk_per_trade: float = 10.0
    max_daily_risk: float = 150.0

from live_unified_predictor import *
