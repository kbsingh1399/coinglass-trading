import numpy as np
import pandas as pd
import six_strategy_engine as sse
import train_six_strategy as tss

def test_all_signal_parity():
    np.random.seed(42)
    n = 1000
    df = pd.DataFrame({
        'mc': np.random.choice([-1, 0, 1], size=n),
        'p8': np.random.uniform(-1.0, 1.0, size=n),
        'ef_slope': np.random.uniform(-2.0, 2.0, size=n),
        'vr5': np.random.uniform(0.1, 2.0, size=n),
        'rsi': np.random.uniform(10.0, 90.0, size=n),
        'ls': np.random.uniform(0.5, 3.0, size=n),
        'lsm': np.random.uniform(0.5, 3.0, size=n),
        'll': np.random.uniform(0.0, 100000.0, size=n),
        'llm': np.random.uniform(0.0, 100000.0, size=n),
        'vr': np.random.uniform(0.1, 3.0, size=n),
        'zc20': np.random.uniform(-2.0, 2.0, size=n),
        'oicc': np.random.uniform(-1.0, 1.0, size=n)
    })
    
    strategies = [
        ('S1', sse.make_signal_s1, tss.make_signal_s1_vec),
        ('S2', sse.make_signal_s2, tss.make_signal_s2_vec),
        ('S3', sse.make_signal_s3, tss.make_signal_s3_vec),
        ('S4', sse.make_signal_s4, tss.make_signal_s4_vec),
        ('S5', sse.make_signal_s5, tss.make_signal_s5_vec),
        ('S6', sse.make_signal_s6, tss.make_signal_s6_vec),
    ]
    
    all_passed = True
    for name, row_fn, vec_fn in strategies:
        row_res = np.array([row_fn(row) for _, row in df.iterrows()])
        vec_res = vec_fn(df)
        diff = np.where(row_res != vec_res)[0]
        if len(diff) == 0:
            print(f"[PASS] {name}: 100% Signal Parity across {n} synthetic bars (Entries: {np.count_nonzero(row_res)})")
        else:
            print(f"[FAIL] {name}: {len(diff)} mismatches found at indices {diff[:5]}")
            all_passed = False
            
    assert all_passed, "Signal parity failed!"
    print("ALL 6 STRATEGY SIGNALS ACHIEVE 100% PARITY!")

if __name__ == '__main__':
    test_all_signal_parity()
