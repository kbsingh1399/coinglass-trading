"""
signals_shared.py — Canonical Signal Definitions (Fable5-Fix-4.1)
==================================================================
Single source of truth for all 6 strategy signal functions.
Imported by BOTH run_all_6.py (backtest) and live_unified_predictor.py (live).

Previously, live signal branches in live_unified_predictor.py diverged from
the validated walk-forward definitions in run_all_6.py across all 6 strategies:
- S1 live: p8 < -0.20, no macro filter, llm*2.0 vs backtest llm*1.2
- S3 live: added rsi<45 and 5x deeper pullback threshold
- S2/S5/S6: entirely different formulas

This file locks the validated backtest formulas as the live signal gate.
Any future change to a signal MUST be made here and re-validated via run_all_6.py
before being deployed to live.

Fable 5 Audit Reference: Layer 4, Finding 4.1 (CRITICAL)
"""
import numpy as np
import pandas as pd


def _get(df: pd.DataFrame, col: str, default=0.0) -> "pd.Series":
    if col in df.columns:
        return df[col]
    return pd.Series(default, index=df.index)


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 1: Trend Pullback + Liquidation Confirmation
# Validated walk-forward formula from run_all_6.py
# ─────────────────────────────────────────────────────────────────────────────
def make_signal_s1(df: pd.DataFrame) -> np.ndarray:
    """
    S1_Liquidation: Long when in uptrend (mc>0), price pulled back (p8<-0.12),
    AND either liq longs spiked (>120% of mean) OR CVD z-score confirms.
    Short mirror.
    """
    out = np.zeros(len(df), dtype=np.int32)
    ll   = _get(df, "liql").values
    ls   = _get(df, "liqs").values
    llm  = _get(df, "liqlm").values
    lsm  = _get(df, "liqsm").values
    mc   = _get(df, "mc").values
    p8   = _get(df, "p8").values
    zc20 = _get(df, "zc20").values

    mask_l = (mc > 0) & (p8 < -0.12) & ((ll > llm * 1.2) | (zc20 > 0.1))
    out[mask_l] = 1
    mask_s = (mc < 0) & (p8 > 0.12) & ((ls > lsm * 1.2) | (zc20 < -0.1))
    out[mask_s] = -1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 2: Deep Pure Trend (very deep pullback to offset fee)
# ─────────────────────────────────────────────────────────────────────────────
def make_signal_s2(df: pd.DataFrame) -> np.ndarray:
    """
    S2_CVD_Momentum (walk-forward name): Requires extremely deep trend pullback
    (p8 < -0.20) to offset fee. No extra CVD requirement — deep pullback IS the signal.
    """
    out = np.zeros(len(df), dtype=np.int32)
    mc = _get(df, "mc").values
    p8 = _get(df, "p8").values

    out[(mc > 0) & (p8 < -0.20)] = 1
    out[(mc < 0) & (p8 > 0.20)] = -1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 3: Pure Trend Pullback (moderate depth)
# ─────────────────────────────────────────────────────────────────────────────
def make_signal_s3(df: pd.DataFrame) -> np.ndarray:
    """
    S3_Trend_Follow: Moderate pullback (p8 < -0.10) in trend direction.
    No RSI filter — that was a live-only deviation not present in backtest.
    """
    out = np.zeros(len(df), dtype=np.int32)
    mc = _get(df, "mc").values
    p8 = _get(df, "p8").values

    out[(mc > 0) & (p8 < -0.10)] = 1
    out[(mc < 0) & (p8 > 0.10)] = -1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 4: RSI Mean Reversion
# ─────────────────────────────────────────────────────────────────────────────
def make_signal_s4(df: pd.DataFrame) -> np.ndarray:
    """
    S4_Mean_Reversion: Oversold RSI (<35) combined with deep price dislocation (p8<-0.5).
    Short mirror: overbought RSI (>65) + p8>0.5.
    """
    out = np.zeros(len(df), dtype=np.int32)
    r  = _get(df, "rsi", default=50.0).values
    p8 = _get(df, "p8").values

    out[(r < 35) & (p8 < -0.5)] = 1
    out[(r > 65) & (p8 > 0.5)] = -1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 5: Volatility Breakout
# ─────────────────────────────────────────────────────────────────────────────
def make_signal_s5(df: pd.DataFrame) -> np.ndarray:
    """
    S5_Vol_Breakout: Core (deep pullback in trend) OR bonus (moderate pullback + vol spike + CVD).
    Bonus gate requires volume ratio >1.5x mean, CVD z-score confirmation, and neutral RSI.
    """
    out = np.zeros(len(df), dtype=np.int32)
    mc   = _get(df, "mc").values
    p8   = _get(df, "p8").values
    vr   = _get(df, "vr").values
    zc20 = _get(df, "zc20").values
    rsi  = _get(df, "rsi", default=50.0).values

    mask_l_core  = (mc > 0) & (p8 < -0.2)
    mask_s_core  = (mc < 0) & (p8 > 0.2)
    mask_l_bonus = (mc > 0) & (p8 < -0.1) & (vr > 1.5) & (zc20 > 0.15) & (rsi > 25) & (rsi < 75)
    mask_s_bonus = (mc < 0) & (p8 > 0.1)  & (vr > 1.5) & (zc20 < -0.15) & (rsi > 25) & (rsi < 75)

    out[mask_l_core | mask_l_bonus] = 1
    out[mask_s_core | mask_s_bonus] = -1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGY 6: OI Coherence
# ─────────────────────────────────────────────────────────────────────────────
def make_signal_s6(df: pd.DataFrame) -> np.ndarray:
    """
    S6_OI_Coherence: Core (deep pullback in trend) OR bonus (moderate pullback + OI/CVD aligned).
    OI coherence = OI delta and CVD delta both positive (long accumulation) or both negative.
    """
    out = np.zeros(len(df), dtype=np.int32)
    mc   = _get(df, "mc").values
    p8   = _get(df, "p8").values
    oicc = _get(df, "oicc").values
    zc20 = _get(df, "zc20").values

    mask_l_core  = (mc > 0) & (p8 < -0.2)
    mask_s_core  = (mc < 0) & (p8 > 0.2)
    mask_l_bonus = (mc > 0) & (p8 < -0.1) & (oicc != 0) & (oicc > 0.2)  & (zc20 > 0.1)
    mask_s_bonus = (mc < 0) & (p8 > 0.1)  & (oicc != 0) & (oicc < -0.2) & (zc20 < -0.1)

    out[mask_l_core | mask_l_bonus] = 1
    out[mask_s_core | mask_s_bonus] = -1
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Registry — canonical ordered list used by both backtest and live
# ─────────────────────────────────────────────────────────────────────────────
STRATS = [
    ("S1_Liquidation",   make_signal_s1),
    ("S2_CVD_Momentum",  make_signal_s2),
    ("S3_Trend_Follow",  make_signal_s3),
    ("S4_Mean_Reversion", make_signal_s4),
    ("S5_Vol_Breakout",  make_signal_s5),
    ("S6_OI_Coherence",  make_signal_s6),
]

STRAT_MAP = {name: fn for name, fn in STRATS}
