import sys
import os
import time
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Engine_1 import Engine1TradeTracker, EngineConfig, config
from ensemble_strategy_predictor import StrategyConfig
from live_model_trainer import TP_MULT_OPTIONS, TRAIL_ATR_OPTIONS

def test_engine_config_defaults():
    eng_cfg = EngineConfig()
    assert eng_cfg.tp_mult == 5.0, f"Expected 5.0, got {eng_cfg.tp_mult}"
    assert eng_cfg.trail_atr == 0.8, f"Expected 0.8, got {eng_cfg.trail_atr}"

def test_strategy_config_defaults():
    strat_cfg = StrategyConfig()
    assert strat_cfg.tp_mult == 5.0, f"Expected 5.0, got {strat_cfg.tp_mult}"
    assert strat_cfg.trail_atr == 0.8, f"Expected 0.8, got {strat_cfg.trail_atr}"

def test_trainer_options_parity():
    assert TP_MULT_OPTIONS == [5.0], f"Expected [5.0], got {TP_MULT_OPTIONS}"
    assert TRAIL_ATR_OPTIONS == [0.8], f"Expected [0.8], got {TRAIL_ATR_OPTIONS}"

def test_cross_file_parameter_parity():
    eng_cfg = EngineConfig()
    strat_cfg = StrategyConfig()

    assert eng_cfg.tp_mult == strat_cfg.tp_mult == 5.0
    assert eng_cfg.trail_atr == strat_cfg.trail_atr == 0.8
    assert TP_MULT_OPTIONS == [5.0]
    assert TRAIL_ATR_OPTIONS == [0.8]

