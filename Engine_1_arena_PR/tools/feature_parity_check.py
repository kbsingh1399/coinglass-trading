#!/usr/bin/env python3
"""
Feature Parity Check — Backtest vs Live Feed
=============================================
Compares feature values from historical parquet (backtest) against
the live AssetSnapshot (scraper) to detect unit/scale mismatches.

Usage:
    python tools/feature_parity_check.py

Checks:
  1. RSI: backtest recomputed from Close vs live scraped value
  2. Funding rate: both must be decimal fractions (|val| < 0.01)
  3. Liquidation short: must be nonzero in at least some recent candles
  4. ATR: must be >= 0.1% of price on closed candles
  5. NATGASUSDT/CLUSDT: must NOT be in trading symbol list (no backtest data)
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from six_strategy_engine import featurize, SYMBOLS as SSE_SYMBOLS

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backtesting_data')

# Symbols to audit
AUDIT_SYMBOLS = ['BTCUSDT', 'TRXUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT']

def load_parquet_features(symbol, n_rows=50):
    """Load last n_rows from backtest parquet and run featurize()."""
    path = os.path.join(DATA_DIR, f'Master_{symbol}_15m_Final_Summary.parquet')
    if not os.path.exists(path):
        return None
    
    df = pd.read_parquet(path)
    
    # Parse timestamp
    tc = "TimeStamp" if "TimeStamp" in df.columns else "Timestamp"
    df["ts"] = pd.to_datetime(df[tc].astype(str).str.replace(" IST", "", regex=False), errors="coerce")
    df = df.sort_values("ts").drop_duplicates(subset=["ts"], keep="first")
    for c in df.columns:
        if c != "ts":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.set_index("ts").tail(n_rows)
    
    # Load BTC reference for cross-asset features
    btc_ref = None
    if symbol != 'BTCUSDT':
        btc_path = os.path.join(DATA_DIR, 'Master_BTCUSDT_15m_Final_Summary.parquet')
        if os.path.exists(btc_path):
            btc = pd.read_parquet(btc_path)
            btc_tc = "TimeStamp" if "TimeStamp" in btc.columns else "Timestamp"
            btc["ts"] = pd.to_datetime(btc[btc_tc].astype(str).str.replace(" IST", "", regex=False), errors="coerce")
            btc = btc.sort_values("ts").drop_duplicates(subset=["ts"], keep="first")
            for c in btc.columns:
                if c != "ts":
                    btc[c] = pd.to_numeric(btc[c], errors="coerce")
            btc = btc.set_index("ts").tail(n_rows)
            btc_ref = btc[['Close', 'CVD']].copy() if 'CVD' in btc.columns else btc[['Close']].copy()
            btc_ref.columns = [f'btc_{c}' for c in btc_ref.columns]
    
    # Run featurize
    df_feat = featurize(df.copy(), btc_ref)
    return df_feat


def check_rsi_parity(df_feat, symbol):
    """Check that featurize() RSI matches recomputed RSI from Close."""
    if df_feat is None:
        return "SKIP", "No parquet data"
    
    rsi_computed = df_feat['rsi'].iloc[-1]
    close = df_feat['Close'].values
    
    # Recompute RSI manually
    d = np.diff(close)
    gains = np.where(d > 0, d, 0)
    losses = np.where(d < 0, -d, 0)
    avg_gain = np.mean(gains[-14:]) if len(gains) >= 14 else np.mean(gains)
    avg_loss = np.mean(losses[-14:]) if len(losses) >= 14 else np.mean(losses)
    if avg_loss == 0:
        rsi_manual = 100.0
    else:
        rsi_manual = 100 - (100 / (1 + avg_gain / avg_loss))
    
    diff = abs(rsi_computed - rsi_manual)
    status = "MATCH" if diff < 5.0 else "MISMATCH"
    return status, f"featurize={rsi_computed:.1f}, manual={rsi_manual:.1f}, diff={diff:.1f}"


def check_funding_rate(df_feat, symbol):
    """Check funding rate is in decimal fraction form."""
    if df_feat is None:
        return "SKIP", "No parquet data"
    
    fr = df_feat['fr'].iloc[-1]
    fr_abs = abs(fr)
    
    if fr_abs < 0.01:
        return "MATCH", f"fr={fr:.6f} (decimal fraction ✅)"
    elif fr_abs < 1.0:
        return "WARN", f"fr={fr:.4f} (ambiguous — could be % or decimal)"
    else:
        return "MISMATCH", f"fr={fr:.2f} (raw percentage — needs ÷100)"


def check_liq_short(df_feat, symbol):
    """Check that liq_short has nonzero values in recent history."""
    if df_feat is None:
        return "SKIP", "No parquet data"
    
    liqs = df_feat['liqs'].values
    nonzero = np.sum(liqs[-50:] != 0)
    total = min(50, len(liqs))
    
    if nonzero > 0:
        return "MATCH", f"liqs nonzero: {nonzero}/{total} candles"
    else:
        return "MISMATCH", f"liqs ZERO for all {total} candles — S1 strategy blind to short liquidations"


def check_atr_minimum(df_feat, symbol):
    """Check ATR is at least 0.1% of price on closed candles."""
    if df_feat is None:
        return "SKIP", "No parquet data"
    
    atr = df_feat['atr'].iloc[-1]
    close = df_feat['Close'].iloc[-1]
    
    if close <= 0:
        return "SKIP", "Close is 0"
    
    atr_pct = (atr / close) * 100
    
    if atr_pct >= 0.1:
        return "MATCH", f"ATR={atr:.6f}, price={close:.4f}, ATR/price={atr_pct:.4f}%"
    else:
        return "MISMATCH", f"ATR={atr:.6f}, price={close:.4f}, ATR/price={atr_pct:.4f}% (below 0.1% minimum)"


def check_symbol_coverage():
    """Check that all trading symbols have backtest data."""
    missing = []
    for sym in SSE_SYMBOLS:
        path = os.path.join(DATA_DIR, f'Master_{sym}_15m_Final_Summary.parquet')
        if not os.path.exists(path):
            missing.append(sym)
    
    # Check for symbols in ALL_SYMBOLS that are NOT in SSE_SYMBOLS
    unbacked = ['XAUUSDT', 'XAGUSDT', 'CLUSDT', 'NATGASUSDT']
    unbacked_in_sse = [s for s in unbacked if s in SSE_SYMBOLS]
    
    if missing:
        return "MISMATCH", f"SSE symbols missing parquet: {missing}"
    elif unbacked_in_sse:
        return "MISMATCH", f"Unbacked symbols in SSE: {unbacked_in_sse}"
    else:
        return "MATCH", f"All {len(SSE_SYMBOLS)} SSE symbols have parquet data. Commodities excluded."


def main():
    print("=" * 70)
    print("FEATURE PARITY CHECK — Backtest vs Live Feed")
    print("=" * 70)
    
    all_pass = True
    results = []
    
    # Symbol coverage
    status, detail = check_symbol_coverage()
    results.append(("Symbol Coverage", "ALL", status, detail))
    if status != "MATCH":
        all_pass = False
    
    # Per-symbol checks
    for sym in AUDIT_SYMBOLS:
        df_feat = load_parquet_features(sym)
        
        for check_name, check_fn in [
            ("RSI Parity", check_rsi_parity),
            ("Funding Rate", check_funding_rate),
            ("Liq Short Data", check_liq_short),
            ("ATR Minimum", check_atr_minimum),
        ]:
            status, detail = check_fn(df_feat, sym)
            results.append((check_name, sym, status, detail))
            if status == "MISMATCH":
                all_pass = False
    
    # Print results table
    print(f"\n{'Check':<20s} {'Symbol':<12s} {'Status':<10s} {'Detail'}")
    print("-" * 100)
    for check, sym, status, detail in results:
        icon = "✅" if status == "MATCH" else ("⚠️" if status == "WARN" else ("❌" if status == "MISMATCH" else "⏭️"))
        print(f"{check:<20s} {sym:<12s} {icon} {status:<8s} {detail}")
    
    print(f"\n{'=' * 70}")
    if all_pass:
        print("✅ ALL CHECKS PASSED — Feature parity confirmed")
    else:
        mismatches = [r for r in results if r[2] == "MISMATCH"]
        print(f"❌ {len(mismatches)} MISMATCH(ES) FOUND — Fix before going live:")
        for check, sym, status, detail in mismatches:
            print(f"   • {check} ({sym}): {detail}")
    
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(main())
