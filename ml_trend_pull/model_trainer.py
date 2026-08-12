"""
ML Trend Pull — Model Trainer
===================================
Walk-Forward Ensemble (LightGBM + XGBoost + CatBoost) training pipeline.
Run weekly (or on-demand) to retrain models on latest data.
Uses exact parameters from agent5_configs
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import lightgbm as lgb
import xgboost as xgb
from catboost import CatBoostClassifier
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')

import importlib.machinery
import importlib.util
_DIR = os.path.dirname(os.path.abspath(__file__))
_ub_path = os.path.join(_DIR, 'unified_backtest.py')
_loader = importlib.machinery.SourceFileLoader('trend_pull_ub_local', _ub_path)
_spec = importlib.util.spec_from_loader('trend_pull_ub_local', _loader)
_ub_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_ub_mod)

load_asset = _ub_mod.load_asset
prep = _ub_mod.prep
NUM_LEAVES = getattr(_ub_mod, 'NUM_LEAVES', 31)
MAX_BARS = getattr(_ub_mod, 'MAX_BARS', 96)
build_labels_fast = _ub_mod.build_labels_fast

local_backtest_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backtesting_data"))
DATA_DIR = local_backtest_dir if os.path.exists(local_backtest_dir) else r'G:\My Drive\_Trading_Data\15m\parquet'
MODEL_DIR = os.path.join(_DIR, "models")
os.makedirs(MODEL_DIR, exist_ok=True)

LGB_PARAMS = {
    'objective': 'binary',
    'metric': 'binary_logloss',
    'learning_rate': 0.05,
    'num_leaves': NUM_LEAVES,
    'verbose': -1,
    'n_jobs': 1,
}

def train_models():
    print(f"\n{'='*60}")
    print(f"ML TREND PULL — LIVE MODEL TRAINER")
    print(f"{'='*60}")
    print(f"  Data dir: {DATA_DIR}")
    print(f"  Model dir: {MODEL_DIR}")
    
    target_assets = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT',
        'TRXUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT', 'LTCUSDT', 'NEARUSDT', 'SUIUSDT'
    ]
    print(f"  Assets to train: {len(target_assets)}")

    # Load BTC reference for CVD
    print(f"\n[1/4] Loading BTC reference...")
    btc = load_asset('BTCUSDT')
    if btc.empty:
        print("ERROR: BTC data required for cross-asset features.")
        return
    btc_ref = btc[['Close', 'CVD']].copy()
    btc_ref.columns = ['btc_Close', 'btc_CVD']

    configs_dir = os.path.join(_DIR, "agent5_configs")
    manifest = {}

    for sym in target_assets:
        print(f"\nProcessing {sym}...")
        cfg_path = os.path.join(configs_dir, f"{sym}.json")
        if not os.path.exists(cfg_path):
            print(f"  Skipping {sym} - no config file found at {cfg_path}")
            continue
            
        with open(cfg_path, 'r') as f:
            cfg = json.load(f)
            
        if cfg.get('score', -99999) <= 0:
            print(f"  Skipping {sym} - optimizer score is non-positive ({cfg.get('score')})")
            continue

        df = load_asset(sym)
        if df.empty:
            print(f"  Skipping {sym} - no data")
            continue
            
        sl_mult = cfg.get('sl_mult', 1.0)
        tp_mult = cfg.get('tp_mult', 5.0)
        window_months = cfg.get('window_size', 3)
        
        # 2. Feature engineering
        df, feats = prep(df.copy(), btc_ref)
        df = df.reset_index()
        
        # 3. Build labels using Optuna params
        df['lab_long'] = build_labels_fast(df, 1, tp_mult, sl_mult)
        df['lab_short'] = build_labels_fast(df, -1, tp_mult, sl_mult)
        
        # 4. Training & OOS Validation Split (80% In-Sample, 20% Out-Of-Sample Holdout)
        cutoff_start = df['ts'].max() - pd.DateOffset(months=window_months)
        train_mask = (df['ts'] >= cutoff_start)
        
        X_full = df.loc[train_mask, feats]
        y_full_long = df.loc[train_mask, 'lab_long']
        y_full_short = df.loc[train_mask, 'lab_short']
        
        if len(X_full) < 200:
            print(f"  {sym}: Insufficient training data ({len(X_full)} rows).")
            continue
            
        split_idx = int(len(X_full) * 0.80)
        X_tr, y_tr_long, y_tr_short = X_full.iloc[:split_idx], y_full_long.iloc[:split_idx], y_full_short.iloc[:split_idx]
        X_val, y_val_long, y_val_short = X_full.iloc[split_idx:], y_full_long.iloc[split_idx:], y_full_short.iloc[split_idx:]
        
        print(f"  Training on {len(X_tr)} IS bars, validating on {len(X_val)} OOS bars (Window: {window_months}M)...")
        
        # 5. Train & Save Models with OOS Early Stopping
        # 5a. LightGBM
        ds_tr_long = lgb.Dataset(X_tr, y_tr_long)
        ds_val_long = lgb.Dataset(X_val, y_val_long, reference=ds_tr_long)
        ds_tr_short = lgb.Dataset(X_tr, y_tr_short)
        ds_val_short = lgb.Dataset(X_val, y_val_short, reference=ds_tr_short)

        ml = lgb.train(LGB_PARAMS, ds_tr_long, 120, valid_sets=[ds_val_long], callbacks=[lgb.early_stopping(15, verbose=False)])
        ms = lgb.train(LGB_PARAMS, ds_tr_short, 120, valid_sets=[ds_val_short], callbacks=[lgb.early_stopping(15, verbose=False)])
        
        # 5b. XGBoost
        # Try GPU acceleration, fallback to CPU
        try:
            xgb_l = xgb.XGBClassifier(n_estimators=120, learning_rate=0.05, max_depth=5, eval_metric='logloss', tree_method='hist', device='cuda', early_stopping_rounds=15, verbosity=0)
            xgb_s = xgb.XGBClassifier(n_estimators=120, learning_rate=0.05, max_depth=5, eval_metric='logloss', tree_method='hist', device='cuda', early_stopping_rounds=15, verbosity=0)
            xgb_l.fit(X_tr, y_tr_long, eval_set=[(X_val, y_val_long)], verbose=False)
            xgb_s.fit(X_tr, y_tr_short, eval_set=[(X_val, y_val_short)], verbose=False)
        except Exception:
            xgb_l = xgb.XGBClassifier(n_estimators=120, learning_rate=0.05, max_depth=5, eval_metric='logloss', tree_method='hist', device='cpu', early_stopping_rounds=15, verbosity=0)
            xgb_s = xgb.XGBClassifier(n_estimators=120, learning_rate=0.05, max_depth=5, eval_metric='logloss', tree_method='hist', device='cpu', early_stopping_rounds=15, verbosity=0)
            xgb_l.fit(X_tr, y_tr_long, eval_set=[(X_val, y_val_long)], verbose=False)
            xgb_s.fit(X_tr, y_tr_short, eval_set=[(X_val, y_val_short)], verbose=False)
        
        # 5c. CatBoost
        cb_l = CatBoostClassifier(iterations=120, learning_rate=0.05, depth=5, verbose=0, thread_count=1, early_stopping_rounds=15)
        cb_s = CatBoostClassifier(iterations=120, learning_rate=0.05, depth=5, verbose=0, thread_count=1, early_stopping_rounds=15)
        cb_l.fit(X_tr, y_tr_long, eval_set=(X_val, y_val_long))
        cb_s.fit(X_tr, y_tr_short, eval_set=(X_val, y_val_short))
        
        # Save all 3 models to tmp first, then replace atomically
        lgb_long_tmp = os.path.join(MODEL_DIR, f"{sym}_long_lgb.txt.tmp")
        lgb_short_tmp = os.path.join(MODEL_DIR, f"{sym}_short_lgb.txt.tmp")
        xgb_long_tmp = os.path.join(MODEL_DIR, f"{sym}_long_xgb_tmp.json")
        xgb_short_tmp = os.path.join(MODEL_DIR, f"{sym}_short_xgb_tmp.json")
        cb_long_tmp = os.path.join(MODEL_DIR, f"{sym}_long_cb.cbm.tmp")
        cb_short_tmp = os.path.join(MODEL_DIR, f"{sym}_short_cb.cbm.tmp")

        ml.save_model(lgb_long_tmp)
        ms.save_model(lgb_short_tmp)
        xgb_l.save_model(xgb_long_tmp)
        xgb_s.save_model(xgb_short_tmp)
        cb_l.save_model(cb_long_tmp)
        cb_s.save_model(cb_short_tmp)
        
        os.replace(lgb_long_tmp, os.path.join(MODEL_DIR, f"{sym}_long_lgb.txt"))
        os.replace(lgb_short_tmp, os.path.join(MODEL_DIR, f"{sym}_short_lgb.txt"))
        os.replace(xgb_long_tmp, os.path.join(MODEL_DIR, f"{sym}_long_xgb.json"))
        os.replace(xgb_short_tmp, os.path.join(MODEL_DIR, f"{sym}_short_xgb.json"))
        os.replace(cb_long_tmp, os.path.join(MODEL_DIR, f"{sym}_long_cb.cbm"))
        os.replace(cb_short_tmp, os.path.join(MODEL_DIR, f"{sym}_short_cb.cbm"))
        
        print(f"  Saved {sym} models to {MODEL_DIR}")
        manifest[sym] = {
            "trained_at": datetime.utcnow().isoformat(),
            "config": cfg
        }

    # Write manifest.json to trigger hot-swap
    manifest_path = os.path.join(MODEL_DIR, "manifest.json")
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=4)
        
    print("\n[SUCCESS] All live models trained and ready for Engine_1.py hot-reload.")

if __name__ == '__main__':
    train_models()
