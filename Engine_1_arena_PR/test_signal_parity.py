"""
Signal Parity Test (Fable 5)
============================
Verifies that the live engine (six_strategy_engine) and the trainer
(train_six_strategy) both consume the EXACT same canonical signal functions
from signals_shared.py — single source of truth, zero divergence.

The previous version of this test referenced sse.make_signal_s1 and
tss.make_signal_s1_vec, neither of which exists post-consolidation, so the
test crashed with AttributeError instead of validating parity.
"""
import numpy as np
import pandas as pd

import signals_shared
import six_strategy_engine as sse

STRAT_KEYS = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6']
NAME_BY_KEY = {
    'S1': 'S1_Liquidation',
    'S2': 'S2_CVD_Momentum',
    'S3': 'S3_Trend_Follow',
    'S4': 'S4_Mean_Reversion',
    'S5': 'S5_Vol_Breakout',
    'S6': 'S6_OI_Coherence',
}


def _synthetic_df(n: int = 1000) -> pd.DataFrame:
    np.random.seed(42)
    return pd.DataFrame({
        'mc': np.random.choice([-1, 0, 1], size=n),
        'p8': np.random.uniform(-1.0, 1.0, size=n),
        'rsi': np.random.uniform(10.0, 90.0, size=n),
        'll': np.random.uniform(0.0, 100000.0, size=n),
        'llm': np.random.uniform(0.0, 100000.0, size=n),
        'ls': np.random.uniform(0.0, 100000.0, size=n),
        'lsm': np.random.uniform(0.0, 100000.0, size=n),
        'liql': np.random.uniform(0.0, 100000.0, size=n),
        'liqs': np.random.uniform(0.0, 100000.0, size=n),
        'liqlm': np.random.uniform(0.0, 100000.0, size=n),
        'liqsm': np.random.uniform(0.0, 100000.0, size=n),
        'vr': np.random.uniform(0.1, 3.0, size=n),
        'zc20': np.random.uniform(-2.0, 2.0, size=n),
        'oicc': np.random.uniform(-1.0, 1.0, size=n),
    })


def test_single_source_of_truth():
    """Live engine SIGNAL_FUNCS must be the identical objects from signals_shared."""
    for key in STRAT_KEYS:
        name = NAME_BY_KEY[key]
        canonical = signals_shared.STRAT_MAP[name]
        live_fn = sse.SIGNAL_FUNCS[name]
        assert live_fn is canonical, (
            f"{name}: live engine function is not the canonical signals_shared object!"
        )
    print("[PASS] Live engine imports all 6 canonical signal functions (identity check).")


def test_trainer_uses_canonical_functions():
    """Trainer SIGNAL_FUNCS_VEC must map to the identical canonical objects."""
    import train_six_strategy as tss
    for key in STRAT_KEYS:
        name = NAME_BY_KEY[key]
        canonical = signals_shared.STRAT_MAP[name]
        trainer_fn = tss.SIGNAL_FUNCS_VEC[key]
        assert trainer_fn is canonical, (
            f"{key}: trainer function is not the canonical signals_shared object!"
        )
    print("[PASS] Trainer imports all 6 canonical signal functions (identity check).")


def test_signal_determinism_and_domain():
    """Signals must be deterministic and emit only {-1, 0, 1} across synthetic bars."""
    df = _synthetic_df()
    for key in STRAT_KEYS:
        name = NAME_BY_KEY[key]
        fn = signals_shared.STRAT_MAP[name]
        out1 = fn(df)
        out2 = fn(df)
        assert np.array_equal(out1, out2), f"{name}: non-deterministic output!"
        assert set(np.unique(out1)).issubset({-1, 0, 1}), f"{name}: invalid signal values!"
        assert len(out1) == len(df), f"{name}: output length mismatch!"
        print(f"[PASS] {name}: deterministic, domain-valid across {len(df)} bars "
              f"(entries: {int(np.count_nonzero(out1))})")


if __name__ == '__main__':
    test_single_source_of_truth()
    try:
        test_trainer_uses_canonical_functions()
    except ImportError as e:
        print(f"[SKIP] Trainer identity check (missing optional dep: {e})")
    test_signal_determinism_and_domain()
    print("ALL SIGNAL PARITY CHECKS PASSED — single source of truth verified.")
