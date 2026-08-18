"""
Six Strategy Engine — Unified Live Predictor
=============================================
Ports the exact logic from colab_strategies/run_all_6.py into a live streaming predictor.

Strategies:
  S1 - Liquidation:    Trend pullback + abnormal liquidation spike
  S2 - CVD Momentum:   Tight trend pullback on strong CVD moves
  S3 - Trend Follow:   Classic macro trend pullback (EMA 200/800)
  S4 - Mean Reversion: RSI extremes with deep pullback
  S5 - Vol Breakout:   Trend pullback + elevated volatility + CVD
  S6 - OI Coherence:   Trend pullback + OI/CVD directional agreement

All strategies share:
  - Same feature engineering (featurize)
  - Same ML pipeline (LGB + XGB ensemble)
  - Same trade parameters (TP=5R, Trail=0.8ATR, SL=1ATR, max 288 bars)
  - Same walk-forward validation
"""

import os
import sys
import json
import time
import collections
import threading
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from numba import njit

# ─── Constants (match run_all_6.py exactly) ──────────────────────────
TP_MULT = 5.0
TRAIL_ATR = 0.8
SL_MULT = 1.0
MAX_BARS = 288       # 72 hours of 15m bars
RISK_PCT = 0.004     # 0.4% per trade (matches RSK=20 on $5000)
FEE_PCT = 2 * float(os.environ.get("ENGINE_FEE_PER_SIDE", "0.0004"))  # Round-trip fee (centralized)

SYMBOLS = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'ADAUSDT',
    'TRXUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT', 'LTCUSDT', 'NEARUSDT', 'SUIUSDT'
]

STRATEGY_NAMES = {
    'S1': 'S1_Liquidation',
    'S2': 'S2_CVD_Momentum',
    'S3': 'S3_Trend_Follow',
    'S4': 'S4_Mean_Reversion',
    'S5': 'S5_Vol_Breakout',
    'S6': 'S6_OI_Coherence',
}


# ─── Numba Trade Simulation (exact copy from run_all_6.py) ──────────
@njit(fastmath=True, nogil=True)
def _sim_trade(h, l, c, entry_idx, entry, atr, dr):
    """Simulate a single trade forward from entry_idx."""
    n = len(c)
    sd = atr * SL_MULT
    td = atr * TP_MULT
    trd = atr * TRAIL_ATR
    st = entry - sd if dr == 1 else entry + sd
    cs = st  # current stop
    bp = entry  # best price
    ns = st  # new stop
    mx = min(entry_idx + MAX_BARS + 1, n)
    ep = c[mx - 1]  # exit price
    bh = mx - 1 - entry_idx  # bars held

    for j in range(entry_idx + 1, mx):
        if dr == 1:
            if l[j] <= cs:
                ep = cs; bh = j - entry_idx; break
            if h[j] > bp:
                bp = h[j]
            if (bp - entry) >= td:
                ns = bp - trd
            if ns > cs:
                cs = ns
        else:
            if h[j] >= cs:
                ep = cs; bh = j - entry_idx; break
            if l[j] < bp:
                bp = l[j]
            if (entry - bp) >= td:
                ns = bp + trd
            if ns < cs:
                cs = ns

    units = RISK_PCT / sd if sd > 0 else 0
    gross = units * (ep - entry) if dr == 1 else units * (entry - ep)
    fees = units * entry * FEE_PCT / 2.0 + units * abs(ep) * FEE_PCT / 2.0
    net_pnl = gross - fees
    r_mult = net_pnl / (RISK_PCT) if RISK_PCT > 0 else 0
    win = 1.0 if net_pnl > 0 else 0.0
    return net_pnl, r_mult, win, bh


# ─── Z-Score Helper ──────────────────────────────────────────────────
def _zscore(series, window):
    """Rolling z-score."""
    mean = series.rolling(window, min_periods=1).mean()
    std = series.rolling(window, min_periods=1).std().replace(0, 1e-10)
    return (series - mean) / std


# ─── Feature Engineering (exact copy from run_all_6.py) ──────────────
def featurize(df, btc_ref=None):
    """Compute all features needed by the 6 strategies (run_all_6.py parity)."""
    if btc_ref is not None:
        cj = [c for c in btc_ref.columns if c not in df.columns]
        if cj:
            df = df.join(btc_ref[cj], how="left")
        if "btc_CVD" in df.columns:
            df["btc_CVD"] = df["btc_CVD"].ffill().bfill().fillna(0)

    # PARITY: use High-Low range exactly as run_all_6.py does.
    df["atr"] = (df["High"] - df["Low"]).rolling(14, min_periods=1).mean()

    # CVD features
    if "CVD" in df.columns:
        df["cvd_d"] = df["CVD"].diff(5)
        for k in [4, 10, 20]:
            df[f"zc{k}"] = _zscore(df["CVD"], k)
    else:
        df["cvd_d"] = 0.0
    for k in [4, 10, 20]:
        df[f"zc{k}"] = df.get(f"zc{k}", pd.Series(0.0, index=df.index))

    # BTC CVD features
    df["bcvm"] = df["btc_CVD"].diff(2) if "btc_CVD" in df.columns else 0.0
    for k in [4, 10, 20]:
        df[f"zb{k}"] = _zscore(df["btc_CVD"], k) if "btc_CVD" in df.columns else 0.0

    # Macro signal
    df["ef"] = df["Close"].ewm(span=200, min_periods=50).mean()
    df["es"] = df["Close"].ewm(span=800, min_periods=100).mean()
    df["mc"] = np.where(
        (df["ef"] - df["es"]) / df["atr"].replace(0, 1e-10) > 0.5,
        1,
        np.where((df["ef"] - df["es"]) / df["atr"].replace(0, 1e-10) < -0.5, -1, 0),
    )

    # EMA pullbacks
    for s, n in [(8, "e8"), (21, "e21"), (50, "e50")]:
        df[n] = df["Close"].ewm(span=s, min_periods=1).mean()

    atrs = df["atr"].replace(0, 1e-10)
    df["p8"] = (df["Close"] - df["e8"]) / atrs
    df["p21"] = (df["Close"] - df["e21"]) / atrs
    df["p50"] = (df["Close"] - df["e50"]) / atrs

    # RSI
    d = df["Close"].diff()
    g = d.clip(lower=0).rolling(14, min_periods=1).mean()
    l = (-d.clip(upper=0)).rolling(14, min_periods=1).mean()
    df["rsi"] = 100 - (100 / (1 + g / l.replace(0, 1e-10)))

    # Volatility regime
    df["vr"] = _zscore(df["atr"], 100)

    # Liquidation features (same candidate list as run_all_6.py)
    for s, default_col in [("l", "Agg. Liq Long"), ("s", "Agg. Liq Short")]:
        col = None
        candidates = [
            default_col,
            f"liq_{'long' if s == 'l' else 'short'}",
            f"liquidations_{'long' if s == 'l' else 'short'}",
            f"liq{s}",
            f"Agg. Liq. {'Long' if s == 'l' else 'Short'}",
        ]
        for candidate in candidates:
            if candidate in df.columns:
                col = candidate
                break
        if col is not None:
            df[f"liq{s}"] = pd.to_numeric(df[col], errors="coerce").fillna(0).rolling(5, min_periods=1).sum()
            df[f"liq{s}m"] = df[f"liq{s}"].rolling(100, min_periods=1).mean()
        else:
            df[f"liq{s}"] = 0.0
            df[f"liq{s}m"] = 0.0

    # Open Interest
    if "Agg. OI" in df.columns:
        oi = pd.to_numeric(df["Agg. OI"], errors="coerce").ffill()
        df["zoi"] = _zscore(oi, 100)
        df["oid"] = oi.diff(5) / (oi.shift(5) + 1e-10)
        df["oicc"] = np.sign(df["oid"].fillna(0)) * np.sign(df["cvd_d"].fillna(0))
    else:
        df["zoi"] = 0.0
        df["oid"] = 0.0
        df["oicc"] = 0.0

    # LS Ratio
    if "Long/Short Ratio (Account)" in df.columns:
        df["zls"] = _zscore(
            pd.to_numeric(df["Long/Short Ratio (Account)"], errors="coerce").ffill(), 100
        )
    else:
        df["zls"] = 0.0

    # Funding Rate - NO division by 100 (parity with backtest)
    if "Agg. Funding Rate" in df.columns:
        fr = pd.to_numeric(df["Agg. Funding Rate"], errors="coerce").fillna(0)
        df["fr"] = fr
        df["zfr"] = _zscore(fr, 20)
    else:
        df["fr"] = 0.0
        df["zfr"] = 0.0

    # Delta Qty synthesis if missing
    if "Delta Qty" not in df.columns:
        if "Ask Qty" in df.columns and "Bid Qty" in df.columns:
            df["Delta Qty"] = (
                pd.to_numeric(df["Ask Qty"], errors="coerce").fillna(0)
                - pd.to_numeric(df["Bid Qty"], errors="coerce").fillna(0)
            )
        elif "Buy Qty" in df.columns and "Sell Qty" in df.columns:
            df["Delta Qty"] = (
                pd.to_numeric(df["Buy Qty"], errors="coerce").fillna(0)
                - pd.to_numeric(df["Sell Qty"], errors="coerce").fillna(0)
            )

    # Footprint features
    for c in ["Bid Qty", "Ask Qty", "Delta Qty", "Bid Trades", "Ask Trades"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
            df[f"z{c.replace(' ', '_').lower()}"] = _zscore(df[c], 10)
        else:
            df[f"z{c.replace(' ', '_').lower()}"] = 0.0

    if "Buy Qty" in df.columns and "Sell Qty" in df.columns:
        buy = pd.to_numeric(df["Buy Qty"], errors="coerce").fillna(0)
        sell = pd.to_numeric(df["Sell Qty"], errors="coerce").fillna(0)
        df["bsr"] = buy / (buy + sell + 1e-10)
    else:
        df["bsr"] = 0.5

    if "Volume" in df.columns:
        df["vr5"] = df["Volume"] / (df["Volume"].rolling(20, min_periods=1).mean() + 1e-10)
    else:
        df["vr5"] = 1.0

    df = df.fillna(0).replace([np.inf, -np.inf], 0)
    return df


# ─── Signal Generators (exact copy from run_all_6.py) ────────────────
def make_signal_s1(row):
    """S1: Trend pullback + liquidation confirmation (PARITY: no RSI)"""
    mc, p8 = row.get('mc', 0), row.get('p8', 0)
    ll, llm = row.get('liql', 0), row.get('liqlm', 0)
    ls, lsm = row.get('liqs', 0), row.get('liqsm', 0)
    zc20 = row.get('zc20', 0)

    if mc > 0 and p8 < -0.12 and (ll > llm * 1.2 or zc20 > 0.1):
        return 1
    if mc < 0 and p8 > 0.12 and (ls > lsm * 1.2 or zc20 < -0.1):
        return -1
    return 0

def make_signal_s2(row):
    """S2: CVD Momentum — tighter pullback (PARITY: no RSI)"""
    mc, p8 = row.get('mc', 0), row.get('p8', 0)
    if mc > 0 and p8 < -0.25:
        return 1
    if mc < 0 and p8 > 0.25:
        return -1
    return 0

def make_signal_s3(row):
    """S3: Pure trend pullback (PARITY: no RSI)"""
    mc, p8 = row.get('mc', 0), row.get('p8', 0)
    if mc > 0 and p8 < -0.2:
        return 1
    if mc < 0 and p8 > 0.2:
        return -1
    return 0

def make_signal_s4(row):
    """S4: RSI mean reversion"""
    rsi, p8 = row.get('rsi', 50), row.get('p8', 0)
    if rsi < 35 and p8 < -0.5:
        return 1
    if rsi > 65 and p8 > 0.5:
        return -1
    return 0

def make_signal_s5(row):
    """S5: Vol Breakout — trend pullback + vol bonus (PARITY: RSI only on bonus)"""
    mc, p8 = row.get('mc', 0), row.get('p8', 0)
    vr, zc20 = row.get('vr', 0), row.get('zc20', 0)
    rsi = row.get('rsi', 50)  # Only used for bonus path

    # Core: trend pullback like S3 (PARITY: no RSI on core)
    if mc > 0 and p8 < -0.2:
        return 1
    if mc < 0 and p8 > 0.2:
        return -1
    # Bonus: high-vol regime (PARITY: RSI 25-75 range)
    if mc > 0 and p8 < -0.1 and vr > 1.5 and zc20 > 0.15 and 25 < rsi < 75:
        return 1
    if mc < 0 and p8 > 0.1 and vr > 1.5 and zc20 < -0.15 and 25 < rsi < 75:
        return -1
    return 0

def make_signal_s6(row):
    """S6: OI Coherence — trend pullback + OI/CVD bonus (PARITY: no RSI)"""
    mc, p8 = row.get('mc', 0), row.get('p8', 0)
    oicc, zc20 = row.get('oicc', 0), row.get('zc20', 0)

    # Core: trend pullback like S3 (PARITY: no RSI)
    if mc > 0 and p8 < -0.2:
        return 1
    if mc < 0 and p8 > 0.2:
        return -1
    # Bonus: OI-CVD coherence (PARITY: no RSI)
    if mc > 0 and p8 < -0.1 and oicc != 0 and oicc > 0.2 and zc20 > 0.1:
        return 1
    if mc < 0 and p8 > 0.1 and oicc != 0 and oicc < -0.2 and zc20 < -0.1:
        return -1
    return 0

SIGNAL_FUNCS = {
    'S1': make_signal_s1,
    'S2': make_signal_s2,
    'S3': make_signal_s3,
    'S4': make_signal_s4,
    'S5': make_signal_s5,
    'S6': make_signal_s6,
}


# ─── ML Model Training (matches run_all_6.py bmodel) ────────────────
def train_ensemble(X, y):
    """Train LGB + XGB ensemble with feature importance selection."""
    import lightgbm as lgb
    try:
        import xgboost as xgb
        has_xgb = True
    except ImportError:
        has_xgb = False

    if len(X) < 20 or y.sum() < 3 or (len(y) - y.sum()) < 3:
        return None, list(X.columns)

    p = y.sum()
    sw = max(0.1, float((len(y) - p) / p)) if p > 0 else 1.0

    # Feature selection via LGB importance
    sel = lgb.LGBMClassifier(n_estimators=30, max_depth=3, random_state=42,
                              verbose=-1, n_jobs=1, max_bin=31)
    sel.fit(X, y)
    imps = sel.feature_importances_
    cut = np.percentile(imps, 15)
    selected = [c for c, im in zip(X.columns, imps) if im >= cut]
    if len(selected) < 3:
        selected = list(X.columns)

    models = []

    # LightGBM
    m_lgb = lgb.LGBMClassifier(
        max_depth=5, learning_rate=0.02, n_estimators=200,
        scale_pos_weight=sw, random_state=42, n_jobs=1, verbose=-1,
        max_bin=63, min_child_samples=8, subsample=0.8,
        colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=0.1
    )
    m_lgb.fit(X[selected], y)
    models.append(m_lgb)

    # XGBoost
    if has_xgb:
        m_xgb = xgb.XGBClassifier(
            max_depth=4, learning_rate=0.03, n_estimators=200,
            scale_pos_weight=sw, random_state=42, n_jobs=1,
            verbosity=0, subsample=0.8, colsample_bytree=0.8, reg_alpha=0.1
        )
        m_xgb.fit(X[selected], y)
        models.append(m_xgb)

    return models, selected


def predict_ensemble(models, selected_cols, X):
    """Ensemble average prediction with robust column realignment."""
    if not models or not selected_cols:
        return np.full(len(X) if hasattr(X, '__len__') else 1, 0.5, dtype=np.float32)
    
    # Realign columns into exact expected feature order with 0.0 fallback
    X_aligned = pd.DataFrame(index=X.index if isinstance(X, pd.DataFrame) else [0])
    for col in selected_cols:
        if isinstance(X, pd.DataFrame) and col in X.columns:
            X_aligned[col] = pd.to_numeric(X[col], errors='coerce').fillna(0.0).values
        else:
            X_aligned[col] = 0.0

    X_df = X_aligned.astype(np.float32)
    probs = [m.predict_proba(X_df)[:, 1] for m in models]
    return np.mean(probs, axis=0)


# ─── Unified Live Predictor Class ────────────────────────────────────
class LiveSixStrategyPredictor:
    """
    Runs all 6 strategies from run_all_6.py on live streaming data.
    
    On each 15m candle close:
    1. Compute features via featurize()
    2. Generate signals via make_signal_s1..s6
    3. Filter via ML ensemble (if trained)
    4. Dispatch trades via trade_tracker.trigger_entry()
    """

    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self.candles_history: Dict[str, collections.deque] = {}
        self.current_candle: Dict[str, dict] = {}
        self._last_predict_bar: Dict[str, int] = {}
        self._cached_signals: Dict[str, Dict[str, str]] = {s: {} for s in symbols}
        self._lock = threading.RLock()

        # ML models per strategy per symbol
        self.models: Dict[str, Dict[str, Any]] = {k: {} for k in SIGNAL_FUNCS}
        self.selected_cols: Dict[str, Dict[str, list]] = {k: {} for k in SIGNAL_FUNCS}
        self.thresholds: Dict[str, Dict[str, float]] = {k: {s: 0.55 for s in symbols} for k in SIGNAL_FUNCS}

        # BTC reference for cross-asset features
        self.btc_ref = None

        # Adaptive loss tracking: (symbol, direction) -> consecutive SL count
        self._consec_losses: Dict[tuple, int] = {}
        # Adaptive threshold lift: per symbol, extra threshold penalty after losses
        self._thresh_lift: Dict[str, float] = {s: 0.0 for s in symbols}
        # Candle-level direction suspension after excessive losses: (symbol, direction) -> bar until which blocked
        self._dir_suspend_until: Dict[tuple, int] = {}
        self.log_fn = None

        self.load_models()

    def _log(self, msg: str, tag: str = "SixStrategy"):
        if self.log_fn:
            try:
                self.log_fn(msg, tag)
            except Exception:
                pass

    def load_models(self):
        """Load pre-trained models from disk."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        models_dir = os.path.join(base_dir, 'six_strategy_models')
        if not os.path.exists(models_dir):
            print(f"[SixStrategy] No pre-trained models at {models_dir} — will train on first data")
            return

        import pickle
        for strat_key in SIGNAL_FUNCS:
            for sym in self.symbols:
                path = os.path.join(models_dir, f'{strat_key}_{sym}.pkl')
                if os.path.exists(path):
                    try:
                        with open(path, 'rb') as f:
                            data = pickle.load(f)
                        self.models[strat_key][sym] = data['models']
                        self.selected_cols[strat_key][sym] = data['selected_cols']
                        self.thresholds[strat_key][sym] = data.get('threshold', 0.55)
                    except Exception as e:
                        print(f"[SixStrategy] Error loading {strat_key}_{sym}: {e}")

        total = sum(len(v) for v in self.models.values())
        print(f"[SixStrategy] Loaded {total} models across {len(SIGNAL_FUNCS)} strategies")

    def notify_trade_closed(self, trade: dict) -> None:
        """Called by Engine1TradeTracker.on_full_close_callbacks when any trade exits.
        Updates per-symbol adaptive loss counters and ML confidence thresholds.
        """
        symbol = trade.get('symbol', '')
        direction = trade.get('direction', 0)
        reason = trade.get('exit_reason', '')
        pnl = trade.get('pnl_usd', 0.0)

        if not symbol or direction == 0:
            return

        loss_key = (symbol, direction)
        is_loss = reason in ('SL', 'EMERGENCY_HALT') or pnl < 0

        if is_loss:
            prev = self._consec_losses.get(loss_key, 0)
            self._consec_losses[loss_key] = prev + 1
            consec = self._consec_losses[loss_key]

            # Raise ML threshold by 0.05 per consecutive loss (capped at +0.25)
            old_lift = self._thresh_lift.get(symbol, 0.0)
            new_lift = min(0.25, old_lift + 0.05)
            self._thresh_lift[symbol] = new_lift
            self._log(f"{symbol} dir={direction} consecutive SL={consec}, "
                      f"ML thresh lift {old_lift:.2f}->{new_lift:.2f}", "LossFilter")

            # Suspend direction for 3 bars after 3 straight SL losses
            if consec >= 3:
                current_bar = len(self.candles_history.get(symbol, []))
                self._dir_suspend_until[loss_key] = current_bar + 3
                self._log(f"{symbol} dir={direction} SUSPENDED for 3 bars "
                          f"after {consec} consecutive SL losses.", "LossFilter")
        else:
            # Win: reset consecutive loss counter and gradually release threshold lift
            self._consec_losses[loss_key] = 0
            old_lift = self._thresh_lift.get(symbol, 0.0)
            self._thresh_lift[symbol] = max(0.0, old_lift - 0.05)
            if self._dir_suspend_until.get(loss_key, 0) > 0:
                self._dir_suspend_until[loss_key] = 0
            self._log(f"{symbol} dir={direction} WIN — consec reset, "
                      f"thresh lift {old_lift:.2f}->{self._thresh_lift[symbol]:.2f}", "LossFilter")

    def set_history(self, symbol: str, candles):
        """Set historical candle data for a symbol."""
        now_open = int(time.time() // 900) * 900
        cleaned = []
        for c in candles:
            try:
                ot = int(c.get('open_time', 0))
            except Exception:
                continue
            if ot > 0 and ot < now_open:
                row = dict(c)
                row['open_time'] = ot
                cleaned.append(row)

        cleaned.sort(key=lambda r: r['open_time'])
        cleaned = cleaned[-1200:]
        self.candles_history[symbol] = collections.deque(cleaned, maxlen=1200)
        if cleaned:
            self._last_predict_bar[symbol] = 0

    def load_history_from_disk(self, max_candles: int = 250):
        """Load historical candles directly from parquet backtesting data or Binance REST API (zero Excel dependency)."""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(base_dir, "backtesting_data")
        loaded = 0
        
        for sym in self.symbols:
            candles = []
            # 1. Primary Source: Parquet backtesting files in backtesting_data/
            summary_path = os.path.join(data_dir, f"Master_{sym}_15m_Final_Summary.parquet")
            fp_path = os.path.join(data_dir, f"Master_{sym}_15m_Final_Footprint.parquet")
            if os.path.exists(summary_path):
                try:
                    df = pd.read_parquet(summary_path)
                    if os.path.exists(fp_path):
                        try:
                            df_fp = pd.read_parquet(fp_path)
                            cj = [c for c in df_fp.columns if c not in df.columns]
                            if cj:
                                df = df.join(df_fp[cj], how='left')
                        except Exception:
                            pass
                    df = df.tail(max_candles)
                    for idx, row in df.iterrows():
                        d = row.to_dict()
                        if 'open_time' not in d:
                            if hasattr(idx, 'timestamp'):
                                d['open_time'] = int(idx.timestamp())
                            elif 'timestamp' in d:
                                d['open_time'] = int(pd.to_datetime(d['timestamp']).timestamp())
                            else:
                                d['open_time'] = int(time.time() - (len(df) - len(candles)) * 900)
                        o_val = float(d.get('open', d.get('Open', 0.0)))
                        h_val = float(d.get('high', d.get('High', 0.0)))
                        l_val = float(d.get('low', d.get('Low', 0.0)))
                        c_val = float(d.get('close', d.get('Close', 0.0)))
                        v_val = float(d.get('volume', d.get('Volume', 0.0)))
                        d['open'] = d['Open'] = o_val
                        d['high'] = d['High'] = h_val
                        d['low'] = d['Low'] = l_val
                        d['close'] = d['Close'] = c_val
                        d['volume'] = d['Volume'] = v_val
                        d['fut_cvd'] = float(d.get('fut_cvd', d.get('CVD', d.get('futCvd', 0.0))))
                        d['spot_cvd'] = float(d.get('spot_cvd', d.get('Spot_CVD', d.get('spotCvd', 0.0))))
                        d['oi'] = float(d.get('oi', d.get('OI', d.get('open_interest', 0.0))))
                        d['funding'] = float(d.get('funding', d.get('Funding', d.get('funding_rate', 0.0))))
                        d['liq_long'] = float(d.get('liq_long', d.get('Liq_Long', d.get('liquidations_long', 0.0))))
                        d['liq_short'] = float(d.get('liq_short', d.get('Liq_Short', d.get('liquidations_short', 0.0))))
                        d['ls_ratio'] = float(d.get('ls_ratio', d.get('LSR', d.get('lsRatio', 1.0))))
                        candles.append(d)
                except Exception:
                    pass
            
            # 2. Live Secondary Source: Binance Futures REST API klines fallback
            if len(candles) < 20:
                try:
                    import urllib.request, json
                    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=15m&limit={max_candles}"
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        raw = json.loads(resp.read().decode())
                        candles = []
                        for k in raw:
                            o_val = float(k[1])
                            h_val = float(k[2])
                            l_val = float(k[3])
                            c_val = float(k[4])
                            v_val = float(k[5])
                            candles.append({
                                'open_time': int(k[0] // 1000),
                                'open': o_val,
                                'high': h_val,
                                'low': l_val,
                                'close': c_val,
                                'volume': v_val,
                                'Open': o_val,
                                'High': h_val,
                                'Low': l_val,
                                'Close': c_val,
                                'Volume': v_val,
                                'fut_cvd': 0.0,
                                'spot_cvd': 0.0,
                                'oi': 0.0,
                                'funding': 0.0,
                                'liq_long': 0.0,
                                'liq_short': 0.0,
                                'ls_ratio': 1.0,
                            })
                except Exception:
                    pass

            if candles:
                self.set_history(sym, candles[-max_candles:])
                loaded += 1

        print(f"[SixStrategy] Successfully seeded history for {loaded}/{len(self.symbols)} symbols (max {max_candles} candles window, zero Excel dependency).")
        self._precompute_initial_indicators()
        print("[SixStrategy] Precomputed initial indicators for all symbols.")

    def _precompute_initial_indicators(self):
        """Precompute rolling indicators across all loaded symbol histories so all metrics are available immediately."""
        btc_ref = None
        if 'BTCUSDT' in self.candles_history:
            btc_df = self._build_df('BTCUSDT')
            if btc_df is not None and len(btc_df) >= 20:
                btc_ref = btc_df[['Close', 'CVD']].copy() if 'CVD' in btc_df.columns else btc_df[['Close']].copy()
                btc_ref.columns = [f'btc_{c}' for c in btc_ref.columns]

        for sym, hist in self.candles_history.items():
            if not hist or len(hist) < 20:
                continue
            try:
                df = self._build_df(sym)
                if df is None or len(df) < 20:
                    continue
                df = featurize(df.copy(), btc_ref if sym != 'BTCUSDT' else None)
                last_row = df.iloc[-1].to_dict()
                atr_val = float(last_row.get('atr', 0.0))
                self._cached_signals[sym] = {
                    'armed_str': 'READY',
                    'atr_val': atr_val,
                    'ema_8': float(last_row.get('e8', 0.0)),
                    'ema_21': float(last_row.get('e21', 0.0)),
                    'ema_50': float(last_row.get('e50', 0.0)),
                    'ema_200': float(last_row.get('ef', 0.0)),
                    'ema_800': float(last_row.get('es', 0.0)),
                    'atr_14': atr_val,
                    'rsi': float(last_row.get('rsi', 50.0)),
                    'zc4': float(last_row.get('zc4', 0.0)),
                    'zc10': float(last_row.get('zc10', 0.0)),
                    'zc20': float(last_row.get('zc20', 0.0)),
                    'zb4': float(last_row.get('zb4', 0.0)),
                    'zb10': float(last_row.get('zb10', 0.0)),
                    'zb20': float(last_row.get('zb20', 0.0)),
                    'vr': float(last_row.get('vr', 0.0)),
                    'zoi': float(last_row.get('zoi', 0.0)),
                    'zls': float(last_row.get('zls', 0.0)),
                    'zfr': float(last_row.get('zfr', 0.0)),
                    'p8': float(last_row.get('p8', 0.0)),
                    'p21': float(last_row.get('p21', 0.0)),
                    'p50': float(last_row.get('p50', 0.0)),
                }
            except Exception:
                pass

    def on_tick_update(self, symbol: str, snap, trade_tracker=None):
        """Called on every tick. Only runs prediction on candle close."""
        with self._lock:
            return self._on_tick_locked(symbol, snap, trade_tracker)

    def _on_tick_locked(self, symbol, snap, trade_tracker):
        if snap.price <= 0:
            return snap

        now = time.time()
        open_time = int(now // 900) * 900

        if symbol not in self.candles_history:
            self.candles_history[symbol] = collections.deque(maxlen=1200)

        history = self.candles_history[symbol]

        # Candle rollover
        if symbol not in self.current_candle or self.current_candle[symbol].get('open_time') != open_time:
            prev = self.current_candle.get(symbol)
            if prev and int(prev.get('open_time', 0)) < open_time:
                prev_ot = int(prev['open_time'])
                if not history or int(history[-1].get('open_time', 0)) != prev_ot:
                    history.append(dict(prev))
            cur_open = getattr(snap, 'open', 0.0) or snap.price
            cur_high = max(getattr(snap, 'high', 0.0), snap.price)
            cur_low = min(getattr(snap, 'low', 0.0) if getattr(snap, 'low', 0.0) > 0 else snap.price, snap.price)
            self.current_candle[symbol] = {
                'open_time': open_time, 'open': cur_open, 'high': cur_high,
                'low': cur_low, 'close': snap.price, 'volume': snap.volume,
                'fut_cvd': snap.fut_cvd, 'spot_cvd': snap.spot_cvd,
                'funding': snap.funding, 'liq_long': snap.liq_long,
                'liq_short': snap.liq_short, 'ls_ratio': snap.ls_ratio,
                'oi': snap.oi, 'coins_bid': snap.coins_bid,
                'coins_ask': snap.coins_ask, 'dollars_bid': snap.dollars_bid,
                'dollars_ask': snap.dollars_ask, 'whale_idx': snap.whale_idx,
                'tk_buy_cnt': snap.tk_buy_cnt, 'tk_sell_cnt': snap.tk_sell_cnt,
                'fp_delta': snap.fp_delta,
                'fp_poc': snap.fp_poc,
            }
        else:
            c = self.current_candle[symbol]
            c['close'] = snap.price
            s_high = getattr(snap, 'high', 0.0)
            s_low = getattr(snap, 'low', 0.0)
            if snap.price > c['high']: c['high'] = snap.price
            if s_high > c['high']: c['high'] = s_high
            if snap.price < c['low'] or c['low'] == 0: c['low'] = snap.price
            if s_low > 0 and s_low < c['low']: c['low'] = s_low
            c['volume'] = snap.volume
            c['fut_cvd'] = snap.fut_cvd
            c['spot_cvd'] = snap.spot_cvd
            c['funding'] = snap.funding
            c['liq_long'] = snap.liq_long
            c['liq_short'] = snap.liq_short
            c['ls_ratio'] = snap.ls_ratio
            c['oi'] = snap.oi
            c['coins_bid'] = snap.coins_bid
            c['coins_ask'] = snap.coins_ask
            c['dollars_bid'] = snap.dollars_bid
            c['dollars_ask'] = snap.dollars_ask
            c['whale_idx'] = snap.whale_idx
            c['tk_buy_cnt'] = snap.tk_buy_cnt
            c['tk_sell_cnt'] = snap.tk_sell_cnt
            c['fp_delta'] = snap.fp_delta
            c['fp_poc'] = snap.fp_poc

        # Only predict on candle close
        last_bar = history[-1].get('open_time', 0) if history else 0
        if last_bar == self._last_predict_bar.get(symbol, 0):
            # Interim tick: replay cached signal and enrich with live pullbacks
            cached = self._cached_signals.get(symbol, {})
            armed_str = cached.get('armed_str', '')
            if trade_tracker:
                with trade_tracker.lock:
                    trades = [t for t in trade_tracker.active_trades.values() if t['symbol'] == symbol]
                if trades:
                    parts = []
                    for t in trades:
                        d = 'LONG' if t['direction'] == 1 else 'SHORT'
                        pnl = t.get('live_pnl_pct', 0)
                        sk = t.get('strategy', '?')[:2]
                        parts.append(f"{sk}:{d}({pnl:+.1f}%)")
                    armed_str = ' '.join(parts)
            if not armed_str:
                armed_str = "READY" if len(history) >= 20 else f"WARM({len(history)}/100)"

            e8 = cached.get('ema_8', getattr(snap, 'ema_8', 0.0))
            e21 = cached.get('ema_21', getattr(snap, 'ema_21', 0.0))
            e50 = cached.get('ema_50', getattr(snap, 'ema_50', 0.0))
            atr = cached.get('atr_14', getattr(snap, 'atr_14', 1.0)) or 1.0
            p8 = (snap.price - e8) / atr if e8 > 0 and atr > 0 else cached.get('p8', 0.0)
            p21 = (snap.price - e21) / atr if e21 > 0 and atr > 0 else cached.get('p21', 0.0)
            p50 = (snap.price - e50) / atr if e50 > 0 and atr > 0 else cached.get('p50', 0.0)

            import dataclasses
            return dataclasses.replace(
                snap,
                strategy_armed=armed_str,
                ema_8=e8,
                ema_21=e21,
                ema_50=e50,
                ema_200=cached.get('ema_200', getattr(snap, 'ema_200', 0.0)),
                ema_800=cached.get('ema_800', getattr(snap, 'ema_800', 0.0)),
                atr_14=atr,
                rsi=cached.get('rsi', getattr(snap, 'rsi', 50.0)),
                zc4=cached.get('zc4', getattr(snap, 'zc4', 0.0)),
                zc10=cached.get('zc10', getattr(snap, 'zc10', 0.0)),
                zc20=cached.get('zc20', getattr(snap, 'zc20', 0.0)),
                zb4=cached.get('zb4', getattr(snap, 'zb4', 0.0)),
                zb10=cached.get('zb10', getattr(snap, 'zb10', 0.0)),
                zb20=cached.get('zb20', getattr(snap, 'zb20', 0.0)),
                vr=cached.get('vr', getattr(snap, 'vr', 0.0)),
                zoi=cached.get('zoi', getattr(snap, 'zoi', 0.0)),
                zls=cached.get('zls', getattr(snap, 'zls', 0.0)),
                zfr=cached.get('zfr', getattr(snap, 'zfr', 0.0)),
                p8=p8,
                p21=p21,
                p50=p50,
            )

        if len(history) < 20:
            import dataclasses
            return dataclasses.replace(snap, strategy_armed=f"WARM({len(history)}/100)")

        self._last_predict_bar[symbol] = last_bar

        # Build DataFrame for feature engineering
        try:
            df = self._build_df(symbol)
            if df is None or len(df) < 20:
                import dataclasses
                return dataclasses.replace(snap, strategy_armed=f"WARM({len(history)}/100)")

            # Get BTC reference
            btc_ref = None
            if symbol != 'BTCUSDT' and 'BTCUSDT' in self.candles_history:
                btc_df = self._build_df('BTCUSDT')
                if btc_df is not None:
                    btc_ref = btc_df[['Close', 'CVD']].copy() if 'CVD' in btc_df.columns else btc_df[['Close']].copy()
                    btc_ref.columns = [f'btc_{c}' for c in btc_ref.columns]

            # Featurize
            df = featurize(df.copy(), btc_ref)
            last_row = df.iloc[-1].to_dict()
            
            # PARITY FIX: Use raw ATR without artificial floor
            atr_val = float(last_row.get('atr', 0))
            if atr_val <= 0 or np.isnan(atr_val) or snap.price <= 0:
                return snap

            # Run all 6 strategies
            armed_parts = []

            # GUARD: Skip symbols that have no trained models for ANY strategy.
            # Trading a symbol without backtest-validated models is unvalidated speculation.
            modeled_strategies = {sk for sk in SIGNAL_FUNCS if symbol in self.models.get(sk, {})}
            if not modeled_strategies:
                import dataclasses
                return dataclasses.replace(snap, strategy_armed="NO_MODEL")

            # --- PRICE-ACTION REGIME DIVERGENCE FILTER ---
            # PARITY FIX: Disable unvalidated PA divergence filter
            hist_list = list(history)
            pa_blocks: set = set()

            current_bar_index = len(hist_list)

            for strat_key, signal_func in SIGNAL_FUNCS.items():
                direction = signal_func(last_row)
                if direction == 0:
                    continue

                # Block signals contradicting recent price-action momentum
                if direction in pa_blocks:
                    continue

                # Block if this symbol+direction is suspended after excessive consecutive losses
                suspend_key = (symbol, direction)
                if self._dir_suspend_until.get(suspend_key, 0) > current_bar_index:
                    remaining = self._dir_suspend_until[suspend_key] - current_bar_index
                    self._log(f"{symbol} dir={direction} suspended for {remaining} more bars.", "LossFilter")
                    continue

                strat_name = STRATEGY_NAMES[strat_key]

                # Check for active trade in this strategy
                if trade_tracker:
                    with trade_tracker.lock:
                        has_active = any(
                            t['symbol'] == symbol and t['strategy'] == strat_name
                            for t in trade_tracker.active_trades.values()
                        )
                    if has_active:
                        continue

                # ML filter (if model available)
                if symbol not in self.models.get(strat_key, {}):
                    continue  # Fail-closed: Never trade without an ML model

                try:
                    fcs = self.selected_cols[strat_key][symbol]
                    X = pd.DataFrame([{c: last_row.get(c, 0) for c in fcs}]).astype(np.float32)
                    prob = predict_ensemble(
                        self.models[strat_key][symbol], fcs, X
                    )[0]
                    if not hasattr(self, 'ml_failures'):
                        self.ml_failures = {}
                    self.ml_failures[symbol] = 0

                    # PARITY FIX: Use fixed threshold (no adaptive lift)
                    base_thresh = self.thresholds[strat_key].get(symbol, 0.55)
                    if float(prob) < (float(base_thresh) - 1e-5):
                        continue
                except Exception as e:
                    if not hasattr(self, 'ml_failures'):
                        self.ml_failures = {}
                    self.ml_failures[symbol] = self.ml_failures.get(symbol, 0) + 1
                    self._log(f"ML evaluation failed for {strat_key} {symbol}: {e}", "SixStrategy")
                    continue  # If ML fails, DO NOT let signal through on this bar

                # Compute SL/TP
                sl = snap.price - SL_MULT * atr_val if direction == 1 else snap.price + SL_MULT * atr_val
                tp = snap.price + TP_MULT * atr_val if direction == 1 else snap.price - TP_MULT * atr_val

                # Dispatch trade (trail_act=1.0 corresponds to 1.0x tp_dist = 5.0 * ATR)
                if trade_tracker:
                    trade_tracker.trigger_entry(
                        symbol, strat_name, direction, snap.price,
                        sl, tp, atr_val, macro=int(last_row.get('mc', 0)),
                        vol_regime=float(last_row.get('vr', 0)),
                        risk_mult=1.0, trail_act=1.0, regime_val=0
                    )

                dir_str = 'LONG' if direction == 1 else 'SHORT'
                armed_parts.append(f"{strat_key}:{dir_str}")

            # Cache armed signals and rolling indicator stats for display
            self._cached_signals[symbol] = {
                'armed_str': ' | '.join(armed_parts) if armed_parts else '',
                'atr_val': atr_val,
                'ema_8': float(last_row.get('e8', 0.0)),
                'ema_21': float(last_row.get('e21', 0.0)),
                'ema_50': float(last_row.get('e50', 0.0)),
                'ema_200': float(last_row.get('ef', 0.0)),
                'ema_800': float(last_row.get('es', 0.0)),
                'atr_14': atr_val,
                'rsi': float(last_row.get('rsi', snap.rsi or 50.0)),
                'zc4': float(last_row.get('zc4', 0.0)),
                'zc10': float(last_row.get('zc10', 0.0)),
                'zc20': float(last_row.get('zc20', 0.0)),
                'zb4': float(last_row.get('zb4', 0.0)),
                'zb10': float(last_row.get('zb10', 0.0)),
                'zb20': float(last_row.get('zb20', 0.0)),
                'vr': float(last_row.get('vr', 0.0)),
                'zoi': float(last_row.get('zoi', 0.0)),
                'zls': float(last_row.get('zls', 0.0)),
                'zfr': float(last_row.get('zfr', 0.0)),
                'p8': float(last_row.get('p8', 0.0)),
                'p21': float(last_row.get('p21', 0.0)),
                'p50': float(last_row.get('p50', 0.0)),
            }

        except Exception as e:
            self._log(f"{symbol} error: {e}", "SixStrategy")

        # Replay cached signal
        cached = self._cached_signals.get(symbol, {})
        armed_str = cached.get('armed_str', '')

        # Show active trades
        if trade_tracker:
            with trade_tracker.lock:
                trades = [t for t in trade_tracker.active_trades.values() if t['symbol'] == symbol]
            if trades:
                parts = []
                for t in trades:
                    d = 'LONG' if t['direction'] == 1 else 'SHORT'
                    pnl = t.get('live_pnl_pct', 0)
                    sk = t.get('strategy', '?')[:2]
                    parts.append(f"{sk}:{d}({pnl:+.1f}%)")
                armed_str = ' '.join(parts)
        if not armed_str:
            armed_str = "READY"

        import dataclasses
        enrich_dict = {
            'strategy_armed': armed_str,
            'ema_8': cached.get('ema_8', getattr(snap, 'ema_8', 0.0)),
            'ema_21': cached.get('ema_21', getattr(snap, 'ema_21', 0.0)),
            'ema_50': cached.get('ema_50', getattr(snap, 'ema_50', 0.0)),
            'ema_200': cached.get('ema_200', getattr(snap, 'ema_200', 0.0)),
            'ema_800': cached.get('ema_800', getattr(snap, 'ema_800', 0.0)),
            'atr_14': cached.get('atr_14', getattr(snap, 'atr_14', 0.0)),
            'rsi': cached.get('rsi', getattr(snap, 'rsi', 50.0)),
            'zc4': cached.get('zc4', getattr(snap, 'zc4', 0.0)),
            'zc10': cached.get('zc10', getattr(snap, 'zc10', 0.0)),
            'zc20': cached.get('zc20', getattr(snap, 'zc20', 0.0)),
            'zb4': cached.get('zb4', getattr(snap, 'zb4', 0.0)),
            'zb10': cached.get('zb10', getattr(snap, 'zb10', 0.0)),
            'zb20': cached.get('zb20', getattr(snap, 'zb20', 0.0)),
            'vr': cached.get('vr', getattr(snap, 'vr', 0.0)),
            'zoi': cached.get('zoi', getattr(snap, 'zoi', 0.0)),
            'zls': cached.get('zls', getattr(snap, 'zls', 0.0)),
            'zfr': cached.get('zfr', getattr(snap, 'zfr', 0.0)),
            'p8': cached.get('p8', getattr(snap, 'p8', 0.0)),
            'p21': cached.get('p21', getattr(snap, 'p21', 0.0)),
            'p50': cached.get('p50', getattr(snap, 'p50', 0.0)),
        }
        snap = dataclasses.replace(snap, **enrich_dict)
        return snap

    def _build_df(self, symbol):
        """Build a DataFrame from candle history."""
        history = list(self.candles_history.get(symbol, []))
        if not history:
            return None

        df = pd.DataFrame(history)
        # Map to expected column names
        col_map = {
            'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close',
            'volume': 'Volume', 'fut_cvd': 'CVD', 'oi': 'Agg. OI',
            'ls_ratio': 'Long/Short Ratio (Account)', 'funding': 'Agg. Funding Rate',
            'liq_long': 'Agg. Liq Long', 'liq_short': 'Agg. Liq Short',
            'coins_bid': 'Bid Qty', 'coins_ask': 'Ask Qty',
            'dollars_bid': 'USD Long', 'dollars_ask': 'USD Short',
            'tk_buy_cnt': 'Ask Trades', 'tk_sell_cnt': 'Bid Trades',
            'fp_delta': 'Delta Qty', 'fp_poc': 'POC Price',
            'whale_idx': 'Whale Index', 'spot_cvd': 'Spot CVD',
        }
        for old, new in col_map.items():
            if old in df.columns and new not in df.columns:
                df[new] = pd.to_numeric(df[old], errors='coerce').fillna(0)
            elif new in df.columns:
                df[new] = pd.to_numeric(df[new], errors='coerce').fillna(0)

        for req in ('Open', 'High', 'Low', 'Close', 'Volume'):
            if req not in df.columns:
                lower_req = req.lower()
                if lower_req in df.columns:
                    df[req] = pd.to_numeric(df[lower_req], errors='coerce').fillna(0)
                else:
                    return None

        # Timestamp index
        if 'open_time' in df.columns:
            df['ts'] = pd.to_datetime(df['open_time'], unit='s')
            df = df.set_index('ts').sort_index()

        return df
