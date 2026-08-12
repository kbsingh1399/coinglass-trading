import sys
import os
import time
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Engine_1 import Engine1TradeTracker, EngineConfig, config
import six_strategy_engine as sse

def test_engine_config_defaults():
    eng_cfg = EngineConfig()
    assert eng_cfg.tp_mult == 5.0, f"Expected 5.0, got {eng_cfg.tp_mult}"
    assert eng_cfg.trail_atr == 0.8, f"Expected 0.8, got {eng_cfg.trail_atr}"

def test_six_strategy_engine_constants():
    assert sse.TP_MULT == 5.0, f"Expected 5.0, got {sse.TP_MULT}"
    assert sse.TRAIL_ATR == 0.8, f"Expected 0.8, got {sse.TRAIL_ATR}"
    assert sse.SL_MULT == 1.0, f"Expected 1.0, got {sse.SL_MULT}"
    assert sse.MAX_BARS == 288, f"Expected 288, got {sse.MAX_BARS}"

def test_cross_file_parameter_parity():
    eng_cfg = EngineConfig()
    assert eng_cfg.tp_mult == sse.TP_MULT == 5.0
    assert eng_cfg.trail_atr == sse.TRAIL_ATR == 0.8


