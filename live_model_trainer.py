import os
import sys
import numpy as np
import pandas as pd
from numba import njit

TP_MULT_OPTIONS = [5.0]
TRAIL_ATR_OPTIONS = [0.8]
SL_MULT = 1.0

def generate_features_standard(df, btc_ref=None):
    if df is None or len(df) == 0:
        return pd.DataFrame()
    df_feat = df.copy()
    return df_feat

def prep_vwap(df):
    if df is None or len(df) == 0:
        return pd.DataFrame()
    return df.copy()

@njit(fastmath=True)
def rolling_mean_numba(arr, window):
    out = np.empty_like(arr)
    n = len(arr)
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
        else:
            out[i] = np.mean(arr[i - window + 1:i + 1])
    return out

@njit(fastmath=True)
def rolling_zscore_numba(arr, window):
    out = np.empty_like(arr)
    n = len(arr)
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
        else:
            sub = arr[i - window + 1:i + 1]
            s = np.std(sub)
            out[i] = (arr[i] - np.mean(sub)) / (s if s > 1e-10 else 1e-10)
    return out

def predict_model_fast(model, X):
    if hasattr(model, 'predict_proba'):
        return model.predict_proba(X)[:, 1]
    return model.predict(X)

def simulate_trade(h, l, c, i, entry, atr, best_dir, tp_mult=5.0, trail_atr=0.8):
    sl_dist = 1.0 * atr
    tp_dist = tp_mult * atr
    if best_dir == 1:
        sl = entry - sl_dist
        tp = entry + tp_dist
    else:
        sl = entry + sl_dist
        tp = entry - tp_dist
    return sl, tp

def simulate_trades_standard(symbol, df_comb, tp_mult=5.0, trail_atr=0.8):
    return []
