#!/usr/bin/env python3
"""
Train Six-Strategy ML Models
=============================
Generates strategy-specific ML models for all 6 strategies × 14 symbols.

Output: six_strategy_models/{S1-S6}_{SYMBOL}.pkl (84 files total)

Each pickle contains:
  - models: [LGB, XGB] ensemble
  - selected_cols: feature columns used
  - threshold: 0.55 (default probability threshold)

Usage:
  python train_six_strategy.py
"""

import os
import sys
import gc
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Import from six_strategy_engine
from six_strategy_engine import (
    SYMBOLS, featurize, train_ensemble, 
    _sim_trade, STRATEGY_NAMES
)

# Try to import numba version if available
try:
    from six_strategy_engine import gen_trades_numba
    HAS_NUMBA = True
except ImportError:
    HAS_NUMBA = False
    print("[WARN] gen_trades_numba not available, using Python fallback")


# ─── Vectorized Signal Functions (from run_all_6.py) ─────────────────
def make_signal_s1_vec(df):
    """S1: Trend pullback + liquidation confirmation (vectorized)"""
    out = np.zeros(len(df), dtype=np.int32)
    ll = df.get("liql", pd.Series(0, index=df.index)).values
    ls = df.get("liqs", pd.Series(0, index=df.index)).values
    llm = df.get("liqlm", pd.Series(0, index=df.index)).values
    lsm = df.get("liqsm", pd.Series(0, index=df.index)).values
    mc = df.get("mc", pd.Series(0, index=df.index)).values
    p8 = df.get("p8", pd.Series(0, index=df.index)).values
    zc20 = df.get("zc20", pd.Series(0, index=df.index)).values
    mask_l = (mc > 0) & (p8 < -0.12) & ((ll > llm * 1.2) | (zc20 > 0.1))
    out[mask_l] = 1
    mask_s = (mc < 0) & (p8 > 0.12) & ((ls > lsm * 1.2) | (zc20 < -0.1))
    out[mask_s] = -1
    return out

def make_signal_s2_vec(df):
    """S2: CVD Momentum — tighter pullback (vectorized)"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df.get("mc", pd.Series(0, index=df.index)).values
    p8 = df.get("p8", pd.Series(0, index=df.index)).values
    mask_l = (mc > 0) & (p8 < -0.25)
    out[mask_l] = 1
    mask_s = (mc < 0) & (p8 > 0.25)
    out[mask_s] = -1
    return out

def make_signal_s3_vec(df):
    """S3: Pure trend pullback (vectorized)"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df.get("mc", pd.Series(0, index=df.index)).values
    p8 = df.get("p8", pd.Series(0, index=df.index)).values
    mask_l = (mc > 0) & (p8 < -0.2)
    out[mask_l] = 1
    mask_s = (mc < 0) & (p8 > 0.2)
    out[mask_s] = -1
    return out

def make_signal_s4_vec(df):
    """S4: RSI mean reversion (vectorized)"""
    out = np.zeros(len(df), dtype=np.int32)
    rsi = df.get("rsi", pd.Series(50, index=df.index)).values
    p8 = df.get("p8", pd.Series(0, index=df.index)).values
    mask_l = (rsi < 35) & (p8 < -0.5)
    out[mask_l] = 1
    mask_s = (rsi > 65) & (p8 > 0.5)
    out[mask_s] = -1
    return out

def make_signal_s5_vec(df):
    """S5: Vol Breakout — trend pullback core + vol bonus (vectorized)"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df.get("mc", pd.Series(0, index=df.index)).values
    p8 = df.get("p8", pd.Series(0, index=df.index)).values
    vr = df.get("vr", pd.Series(0, index=df.index)).values
    zc20 = df.get("zc20", pd.Series(0, index=df.index)).values
    rsi = df.get("rsi", pd.Series(50, index=df.index)).values
    # Core: trend pullback like S3
    mask_l_core = (mc > 0) & (p8 < -0.2)
    mask_s_core = (mc < 0) & (p8 > 0.2)
    # Bonus: high-vol regime entries
    mask_l_bonus = (mc > 0) & (p8 < -0.1) & (vr > 1.5) & (zc20 > 0.15) & (rsi > 25) & (rsi < 75)
    mask_s_bonus = (mc < 0) & (p8 > 0.1) & (vr > 1.5) & (zc20 < -0.15) & (rsi > 25) & (rsi < 75)
    out[mask_l_core | mask_l_bonus] = 1
    out[mask_s_core | mask_s_bonus] = -1
    return out

def make_signal_s6_vec(df):
    """S6: OI Coherence — trend pullback core + OI/CVD bonus (vectorized)"""
    out = np.zeros(len(df), dtype=np.int32)
    mc = df.get("mc", pd.Series(0, index=df.index)).values
    p8 = df.get("p8", pd.Series(0, index=df.index)).values
    oicc = df.get("oicc", pd.Series(0, index=df.index)).values
    zc20 = df.get("zc20", pd.Series(0, index=df.index)).values
    # Core: trend pullback like S3 (always works)
    mask_l_core = (mc > 0) & (p8 < -0.2)
    mask_s_core = (mc < 0) & (p8 > 0.2)
    # Bonus: OI-CVD coherence signals when data available
    mask_l_bonus = (mc > 0) & (p8 < -0.1) & (oicc != 0) & (oicc > 0.2) & (zc20 > 0.1)
    mask_s_bonus = (mc < 0) & (p8 > 0.1) & (oicc != 0) & (oicc < -0.2) & (zc20 < -0.1)
    out[mask_l_core | mask_l_bonus] = 1
    out[mask_s_core | mask_s_bonus] = -1
    return out

# Map strategy keys to vectorized functions
SIGNAL_FUNCS_VEC = {
    'S1': make_signal_s1_vec,
    'S2': make_signal_s2_vec,
    'S3': make_signal_s3_vec,
    'S4': make_signal_s4_vec,
    'S5': make_signal_s5_vec,
    'S6': make_signal_s6_vec,
}

# ─── Configuration ───────────────────────────────────────────────────
DATA_DIR = Path('backtesting_data')
MODEL_DIR = Path('six_strategy_models')
MODEL_DIR.mkdir(exist_ok=True)

# Trade parameters (match run_all_6.py exactly)
TP_MULT = 5.0
TRAIL_ATR = 0.8
SL_MULT = 1.0
MAX_BARS = 288
RISK_PCT = 0.004
FEE_PCT = 0.0015

# Minimum trades required to train a model
MIN_TRADES = 20
MIN_POSITIVE = 3
MIN_NEGATIVE = 3


# ─── Data Loading (matches run_all_6.py exactly) ────────────────────
def load_symbol_data(symbol: str) -> pd.DataFrame:
    """Load and merge summary + footprint parquet files."""
    summary_path = DATA_DIR / f'Master_{symbol}_15m_Final_Summary.parquet'
    footprint_path = DATA_DIR / f'Master_{symbol}_15m_Final_Footprint.parquet'
    
    if not summary_path.exists():
        print(f"  [WARN] {symbol}: Summary file not found at {summary_path}")
        return pd.DataFrame()
    
    # Load summary
    df = pd.read_parquet(summary_path)
    
    # Parse timestamp
    tc = "TimeStamp" if "TimeStamp" in df.columns else "Timestamp"
    df["ts"] = pd.to_datetime(
        df[tc].astype(str).str.replace(" IST", "", regex=False),
        errors="coerce"
    )
    
    # Load and merge footprint if available
    if footprint_path.exists():
        df_f = pd.read_parquet(footprint_path)
        tcf = "TimeStamp" if "TimeStamp" in df_f.columns else "Timestamp"
        df_f["ts"] = pd.to_datetime(
            df_f[tcf].astype(str).str.replace(" IST", "", regex=False),
            errors="coerce"
        )
        
        # Drop duplicate columns
        dup_cols = [c for c in df_f.columns if c in df.columns and c != "ts"]
        drop_cols = [
            c for c in [
                "Symbol", "POC Price", "Candle #", "Timestamp", 
                "TimeStamp", "time", "Is POC"
            ] + dup_cols if c in df_f.columns
        ]
        if drop_cols:
            df_f = df_f.drop(columns=drop_cols, errors="ignore")
        
        # Merge with backward tolerance
        df = pd.merge_asof(
            df.sort_values("ts"),
            df_f.sort_values("ts"),
            on="ts",
            direction="backward",
            tolerance=pd.Timedelta(minutes=5)
        )
    
    # Rename columns
    col_map = {
        'open': 'Open', 'high': 'High', 'low': 'Low', 
        'close': 'Close', 'volume': 'Volume', 'cvd': 'CVD'
    }
    df = df.rename(columns={c: col_map[c.lower()] for c in df.columns if c.lower() in col_map})
    
    # Drop metadata columns
    drop_cols = [
        c for c in [
            "Symbol", "POC Price", "Candle #", "Timestamp", 
            "TimeStamp", "time", "Is POC"
        ] if c in df.columns
    ]
    if drop_cols:
        df = df.drop(columns=drop_cols, errors="ignore")
    
    # Sort, deduplicate, convert to numeric
    df = df.sort_values("ts").drop_duplicates(subset=["ts"], keep="first")
    for c in df.columns:
        if c != "ts":
            df[c] = pd.to_numeric(df[c], errors="coerce").astype(np.float32)
    
    return df.set_index("ts")


# ─── Trade Generation (Python fallback if numba unavailable) ────────
def gen_trades_python(h, l, c, o, a, sig):
    """Python fallback for trade generation (slower but works without numba)."""
    n = len(c)
    results = []
    i = 200
    cd = 0
    
    while i < n - 100:
        if i >= cd:
            dr = sig[i]
            if dr != 0:
                entry = o[i + 1] if i + 1 < n else c[i]
                av = a[i]
                if av > 0 and not np.isnan(av):
                    net, r, lb, bh = _sim_trade(h, l, c, i, entry, av, int(dr))
                    results.append((i, dr, net, r, lb, bh))
                    cd = i + int(bh) + 2
        i += 1
    
    return results


# ─── Feature Extraction ─────────────────────────────────────────────
def extract_features_and_labels(
    df: pd.DataFrame,
    signal_func_vec,
    btc_ref: Optional[pd.DataFrame] = None
) -> Tuple[pd.DataFrame, pd.Series, List[str]]:
    """
    Generate signals, simulate trades, extract features and labels.
    
    Args:
        df: Raw OHLCV data
        signal_func_vec: Vectorized signal function (works on entire DataFrame)
        btc_ref: BTC reference data for cross-asset features
    
    Returns:
        X: DataFrame of features at entry bars
        y: Series of labels (1=win, 0=loss)
        feature_cols: List of feature column names
    """
    # Featurize
    df_feat = featurize(df.copy(), btc_ref)
    
    # Generate signals (vectorized - works on entire DataFrame)
    signals = signal_func_vec(df_feat)
    
    # Extract arrays for trade simulation
    h = df_feat["High"].values.astype(np.float64)
    l = df_feat["Low"].values.astype(np.float64)
    c = df_feat["Close"].values.astype(np.float64)
    o = df_feat["Open"].values.astype(np.float64)
    a = df_feat["atr"].values.astype(np.float64)
    
    # Simulate trades (always use Python fallback since gen_trades_numba 
    # is not in six_strategy_engine.py, only _sim_trade is)
    trades = gen_trades_python(h, l, c, o, a, signals)
    
    if not trades:
        return pd.DataFrame(), pd.Series(dtype=int), []
    
    # Extract feature columns (exclude metadata and targets)
    exclude_cols = [
        'ts', 'Timestamp', 'TimeStamp', 'Symbol', 'POC Price', 
        'Candle #', 'time', 'Open', 'High', 'Low', 'Close', 'Volume', 
        'Trades', 'btc_Close', 'btc_CVD'
    ]
    
    feature_cols = [
        c for c in df_feat.columns 
        if c not in exclude_cols and pd.api.types.is_numeric_dtype(df_feat[c])
    ]
    
    # Build feature matrix and labels (vectorized)
    trade_indices = [t[0] for t in trades]
    labels = [int(t[4]) for t in trades]
    X = df_feat[feature_cols].iloc[trade_indices].reset_index(drop=True)
    y = pd.Series(labels, dtype=int)
    
    return X, y, feature_cols, trades



# ─── Main Training Loop ─────────────────────────────────────────────
def train_all_strategies():
    """Train models for all 6 strategies × 14 symbols."""
    print("=" * 70)
    print("SIX-STRATEGY ML MODEL TRAINER (CALIBRATED THRESHOLDS)")
    print("=" * 70)
    print(f"Data directory: {DATA_DIR}")
    print(f"Model directory: {MODEL_DIR}")
    print(f"Symbols: {len(SYMBOLS)}")
    print(f"Strategies: {len(SIGNAL_FUNCS_VEC)}")
    print()
    
    # Load BTC reference for cross-asset features
    print("[1/3] Loading BTC reference data...")
    btc_df = load_symbol_data('BTCUSDT')
    if btc_df.empty:
        print("[ERROR] BTC data required for cross-asset features. Exiting.")
        return
    
    btc_ref = btc_df[['Close', 'CVD']].copy() if 'CVD' in btc_df.columns else btc_df[['Close']].copy()
    btc_ref.columns = [f'btc_{c}' for c in btc_ref.columns]
    print(f"  BTC: {len(btc_df)} bars loaded")
    print()
    
    # Train models for each strategy and symbol
    print("[2/3] Training models...")
    print("-" * 70)
    
    total_models = 0
    skipped = 0
    
    for strat_key, signal_func_vec in SIGNAL_FUNCS_VEC.items():
        strat_name = STRATEGY_NAMES[strat_key]
        print(f"\n{'='*70}")
        print(f"STRATEGY: {strat_name}")
        print(f"{'='*70}")
        
        strat_models = 0
        
        for symbol in SYMBOLS:
            print(f"\n  {symbol}: ", end="")
            
            # Load data
            df = load_symbol_data(symbol)
            if df.empty:
                print("SKIP (no data)")
                skipped += 1
                continue
            
            # Get BTC reference (None for BTC itself)
            ref = btc_ref if symbol != 'BTCUSDT' else None
            
            # Extract features and labels
            try:
                X, y, feature_cols, trades = extract_features_and_labels(df, signal_func_vec, ref)
            except Exception as e:
                print(f"ERROR ({e})")
                skipped += 1
                continue
            
            if len(X) == 0:
                print("SKIP (no trades)")
                skipped += 1
                continue
            
            # Check if we have enough data
            if len(X) < MIN_TRADES:
                print(f"SKIP (only {len(X)} trades, need {MIN_TRADES})")
                skipped += 1
                continue
            
            if y.sum() < MIN_POSITIVE or (len(y) - y.sum()) < MIN_NEGATIVE:
                print(f"SKIP (imbalanced: {y.sum()} wins, {len(y)-y.sum()} losses)")
                skipped += 1
                continue
            
            # Train ensemble
            print(f"Training ({len(X)} trades, {y.sum()} wins)... ", end="")
            
            try:
                models, selected_cols = train_ensemble(X[feature_cols], y)
            except Exception as e:
                print(f"ERROR ({e})")
                skipped += 1
                continue
            
            if models is None:
                print("SKIP (training failed)")
                skipped += 1
                continue
            
            # Calculate calibrated optimal probability threshold matching run_all_6.py
            try:
                probs = np.mean([m.predict_proba(X[selected_cols])[:, 1] for m in models], axis=0)
                pdf = pd.DataFrame({
                    'prob': probs,
                    'net_pnl': [t[2] for t in trades],
                    'label': y.values
                })
                
                best_thresh_val = 0.55
                best_score = -1e9
                cap = 5000.0
                min_eval_trades = max(5, int(len(pdf) * 0.05))
                
                for p in np.arange(0.50, 0.90, 0.02):
                    c = pdf[pdf['prob'] >= p]
                    n = len(c)
                    if n < min_eval_trades:
                        continue
                    nw = (c['label'] > 0).sum()
                    wr = (nw / n) * 100.0
                    tp = c['net_pnl'].sum()
                    roi = (tp / cap) * 100.0
                    eq = cap + c['net_pnl'].cumsum()
                    dd = ((eq.cummax() - eq) / eq.cummax() * 100.0).max() if len(eq) > 0 else 0.0
                    if wr >= 35.0 and roi > 0:
                        score = roi * (wr / 100.0) / max(dd, 0.1) * np.log1p(n)
                        if score > best_score:
                            best_thresh_val = float(round(p, 2))
                            best_score = score
                
                filtered_df = pdf[pdf['prob'] >= best_thresh_val]
                calibrated_wr = float((filtered_df['label'] > 0).mean()) if len(filtered_df) > 0 else float(y.mean())
            except Exception:
                best_thresh_val = 0.55
                calibrated_wr = float(y.mean())
            
            # Save model
            output_path = MODEL_DIR / f'{strat_key}_{symbol}.pkl'
            model_data = {
                'models': models,
                'selected_cols': selected_cols,
                'threshold': best_thresh_val,
                'n_trades': len(X),
                'n_wins': int(y.sum()),
                'win_rate': calibrated_wr
            }
            
            with open(output_path, 'wb') as f:
                pickle.dump(model_data, f)
            
            print(f"[OK] Saved (thresh={best_thresh_val:.2f}, {len(selected_cols)} feats, Calibrated WR={calibrated_wr:.1%})")
            strat_models += 1
            total_models += 1
            
            # Cleanup
            del df, X, y, models, selected_cols, model_data
            gc.collect()
        
        print(f"\n  {strat_name}: {strat_models}/{len(SYMBOLS)} models trained")
    
    # Summary
    print(f"\n{'='*70}")
    print("[3/3] TRAINING COMPLETE")
    print(f"{'='*70}")
    print(f"  Total models trained: {total_models}/{len(SYMBOLS) * len(SIGNAL_FUNCS_VEC)}")
    print(f"  Skipped: {skipped}")
    print(f"  Output directory: {MODEL_DIR}")
    print()
    
    if total_models > 0:
        print("[OK] Models ready for live trading!")
        print("  LiveSixStrategyPredictor will load them automatically.")
    else:
        print("[FAIL] No models trained. Check data availability and trade generation.")
    
    print()


# ─── Entry Point ─────────────────────────────────────────────────────
if __name__ == '__main__':
    try:
        train_all_strategies()
    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Training stopped by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Training failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
