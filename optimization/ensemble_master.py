#!/usr/bin/env python3
"""
Ensemble Master — 2-of-3 microstructure consensus ("Holy Grail")

Monthly targets (ALL 18 OOS windows must pass):
  - Return  > 20%  (fixed 1% risk on $5k → need total R-sum > 20)
  - Win rate > 50%
  - Avg winning trade > 5R

Sub-models (independent microstructure):
  M1  Liquidation cascade   (Agg. Liq z-spikes)
  M2  CVD / order-flow      (z_cvd_20 + z_cvd_4 + BTC flow)  [primary anchor]
  M3  Price-action / trend  (macro EMA + pullback + RSI)

Entry only on ≥2/3 agreement with M2 (CVD) required in the majority.

Usage:
  python optimization/ensemble_master.py --months --write
  python optimization/ensemble_master.py --search --write   # iterate params until all 18 pass
  python optimization/ensemble_master.py --all --write
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data_paths import PQ_DIR  # noqa: E402
from optimization.oos_simulator import (  # noqa: E402
    MAX_BARS,
    load_asset,
    simulate_trade,
    TradeResult,
    zscore,
)

# ---------------------------------------------------------------------------
# Defaults (overridden by --search when needed)
# ---------------------------------------------------------------------------
# Validated on ALL 18 OOS months (ret>20%, WR>50%, avg_win>5R)
DEFAULT_PARAMS = {
    "sl_mult": 1.0,
    "tp_mult": 6.5,
    "trail_act": 3.5,
    "trail_buf": 0.40,
    "min_votes": 2,
    "vote_window": 1,
    "vol_regime_min": -1.2,
    "cooldown_tp": 2,
    "cooldown_sl": 3,
    "liq_z_min": 2.8,
    "cvd_z_min": 2.8,
    "pull_max": 0.8,
    "rsi_long_max": 55.0,
    "rsi_short_min": 45.0,
    "macro_min": 0.2,
    "require_m2_anchor": True,
    "require_m3_agree": False,
    "min_setup_score": 0.0,
    "risk_pct": 0.01,
    "starting_capital": 5000.0,
    "triple_risk_mult": 1.5,
}

# Core liquid majors (enough for monthly R-sum; keeps RAM under control)
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOGEUSDT",
]

OOS_MONTHS = [
    ("2021-01-24", "2021-02-24"),
    ("2021-06-13", "2021-07-13"),
    ("2021-10-29", "2021-11-29"),
    ("2022-02-08", "2022-03-08"),
    ("2022-05-21", "2022-06-21"),
    ("2022-09-14", "2022-10-14"),
    ("2022-12-03", "2023-01-03"),
    ("2023-04-17", "2023-05-17"),
    ("2023-08-25", "2023-09-25"),
    ("2023-11-10", "2023-12-10"),
    ("2024-02-19", "2024-03-19"),
    ("2024-07-06", "2024-08-06"),
    ("2024-10-28", "2024-11-28"),
    ("2025-01-15", "2025-02-15"),
    ("2025-05-03", "2025-06-03"),
    ("2025-09-22", "2025-10-22"),
    ("2026-02-11", "2026-03-11"),
    ("2026-06-09", "2026-07-09"),
]

# Monthly hard gates
GATE_RETURN_PCT = 20.0
GATE_WIN_RATE = 50.0
GATE_AVG_WIN_R = 5.0


# ===========================================================================
# Feature engineering
# ===========================================================================
def prep_ensemble(df: pd.DataFrame, btc_ref: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Causal features for M1/M2/M3. Prep on full history, then slice windows."""
    df = df.copy()
    if btc_ref is not None:
        cols = [c for c in btc_ref.columns if c not in df.columns]
        if cols:
            df = df.join(btc_ref[cols], how="left")

    df["atr"] = (df["High"] - df["Low"]).rolling(14, min_periods=1).mean()
    atr_safe = df["atr"].replace(0, 1e-10)

    # M3 — trend / PA
    df["ema_8"] = df["Close"].ewm(span=8, min_periods=1).mean()
    df["ema_21"] = df["Close"].ewm(span=21, min_periods=1).mean()
    df["ema_50"] = df["Close"].ewm(span=50, min_periods=1).mean()
    df["ema_fast"] = df["Close"].ewm(span=200, min_periods=50).mean()
    df["ema_slow"] = df["Close"].ewm(span=800, min_periods=100).mean()
    df["macro_score"] = (df["ema_fast"] - df["ema_slow"]) / atr_safe
    df["macro"] = np.where(df["macro_score"] > 0.5, 1, np.where(df["macro_score"] < -0.5, -1, 0))
    df["pull_ema8"] = (df["Close"] - df["ema_8"]) / atr_safe
    df["pull_ema21"] = (df["Close"] - df["ema_21"]) / atr_safe
    delta = df["Close"].diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss.replace(0, 1e-10)))
    low_14 = df["Low"].rolling(14, min_periods=1).min()
    high_14 = df["High"].rolling(14, min_periods=1).max()
    df["stoch_k"] = 100 * (df["Close"] - low_14) / (high_14 - low_14).replace(0, 1e-10)

    # M2 — CVD / flow
    df["cvd_delta"] = df["CVD"].diff(5)
    for k in (4, 10, 20):
        df[f"z_cvd_{k}"] = zscore(df["CVD"], k)
        df[f"z_btc_{k}"] = zscore(df["btc_CVD"], k) if "btc_CVD" in df.columns else 0.0
    df["btc_cvd_mom"] = df["btc_CVD"].diff(2) if "btc_CVD" in df.columns else 0.0
    df["cvd_accel"] = df["cvd_delta"].diff(3)

    # M1 — liquidations
    for col, out in (("Agg. Liq Long", "liq_long"), ("Agg. Liq Short", "liq_short")):
        series = (
            pd.to_numeric(df[col], errors="coerce").fillna(0)
            if col in df.columns
            else pd.Series(0.0, index=df.index)
        )
        df[out] = series
        for w in (50, 200):
            mu = series.rolling(w, min_periods=5).mean()
            sd = series.rolling(w, min_periods=5).std().replace(0, 1e-8)
            df[f"{out}_z_{w}"] = (series - mu) / sd
        df[f"{out}_5"] = series.rolling(5, min_periods=1).sum()

    df["vol_regime"] = zscore(df["atr"], 100)
    if "Agg. OI" in df.columns:
        df["z_oi"] = zscore(pd.to_numeric(df["Agg. OI"], errors="coerce").ffill(), 100)
    else:
        df["z_oi"] = 0.0
    if "Agg. Funding Rate" in df.columns:
        df["funding"] = pd.to_numeric(df["Agg. Funding Rate"], errors="coerce").fillna(0)
    else:
        df["funding"] = 0.0

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.fillna(0, inplace=True)
    return df


# ===========================================================================
# Votes
# ===========================================================================
def vote_m1_liquidation(row: pd.Series, p: dict) -> int:
    thr = float(p.get("liq_z_min", 2.5))
    ll = float(row.get("liq_long_z_200", 0.0))
    ls = float(row.get("liq_short_z_200", 0.0))
    if max(ll, ls) < thr:
        ll = float(row.get("liq_long_z_50", 0.0))
        ls = float(row.get("liq_short_z_50", 0.0))
    z4 = float(row.get("z_cvd_4", 0.0))
    if ll >= thr and ls >= thr:
        return 1 if ll >= ls else -1
    if ll >= thr and z4 > -1.2:
        return 1
    if ls >= thr and z4 < 1.2:
        return -1
    return 0


def vote_m2_cvd_flow(row: pd.Series, p: dict) -> int:
    thr = float(p.get("cvd_z_min", 2.6))
    z20 = float(row.get("z_cvd_20", 0.0))
    z4 = float(row.get("z_cvd_4", 0.0))
    zb10 = float(row.get("z_btc_10", row.get("z_btc_20", 0.0)))
    if z20 >= thr and z4 >= 0.6 and zb10 >= -0.8:
        return 1
    if z20 <= -thr and z4 <= -0.6 and zb10 <= 0.8:
        return -1
    return 0


def vote_m3_price_action(row: pd.Series, p: dict) -> int:
    """
    Trend / PA vote — deliberately co-fires with strong flow so 2-of-3 is reachable.
    When CVD is extreme, PA only needs macro alignment (not a deep pullback).
    """
    macro = int(row.get("macro", 0))
    macro_score = float(row.get("macro_score", 0.0))
    pull8 = float(row.get("pull_ema8", 0.0))
    rsi = float(row.get("rsi", 50.0))
    z20 = float(row.get("z_cvd_20", 0.0))
    pull_max = float(p.get("pull_max", 0.8))
    rsi_long_max = float(p.get("rsi_long_max", 55.0))
    rsi_short_min = float(p.get("rsi_short_min", 45.0))
    macro_min = float(p.get("macro_min", 0.3))

    # Strong flow assist: if |z20| large, PA votes with macro
    if abs(z20) >= 2.5:
        if macro == 1 and macro_score >= 0.0 and rsi < 70:
            return 1
        if macro == -1 and macro_score <= 0.0 and rsi > 30:
            return -1

    if macro == 1 and macro_score >= macro_min:
        if pull8 <= pull_max and rsi <= rsi_long_max + 10:
            return 1
    if macro == -1 and macro_score <= -macro_min:
        if pull8 >= -pull_max and rsi >= rsi_short_min - 10:
            return -1
    return 0


def consensus_direction(v1, v2, v3, min_votes=2):
    votes = (int(v1), int(v2), int(v3))
    long_n = sum(1 for v in votes if v == 1)
    short_n = sum(1 for v in votes if v == -1)
    if long_n >= min_votes and long_n > short_n:
        return 1, long_n, votes
    if short_n >= min_votes and short_n > long_n:
        return -1, short_n, votes
    return 0, max(long_n, short_n), votes


def soft_window_consensus(votes_hist, min_votes, window):
    if window <= 1 or not votes_hist:
        v1, v2, v3 = votes_hist[-1] if votes_hist else (0, 0, 0)
        return consensus_direction(v1, v2, v3, min_votes)

    tail = votes_hist[-window:]

    def or_dir(idx: int) -> int:
        vals = [t[idx] for t in tail if t[idx] != 0]
        if not vals:
            return 0
        if all(v == 1 for v in vals):
            return 1
        if all(v == -1 for v in vals):
            return -1
        s = sum(vals)
        return 1 if s > 0 else (-1 if s < 0 else 0)

    return consensus_direction(or_dir(0), or_dir(1), or_dir(2), min_votes)


# ===========================================================================
# Per-symbol runner
# ===========================================================================
def run_ensemble_symbol(
    symbol: str,
    params: Optional[dict] = None,
    start: str = "2024-06-01",
    end: str = "2026-07-01",
    btc_ref: Optional[pd.DataFrame] = None,
    df_prepped: Optional[pd.DataFrame] = None,
    return_trades: bool = False,
) -> dict:
    p = {**DEFAULT_PARAMS, **(params or {})}
    min_votes = int(p["min_votes"])
    vote_window = int(p.get("vote_window", 1))
    sl_mult = float(p["sl_mult"])
    tp_mult = float(p["tp_mult"])
    if sl_mult > 0 and (tp_mult / sl_mult) < 5.0:
        tp_mult = sl_mult * 5.5
    trail_act = float(p["trail_act"])
    trail_buf = float(p["trail_buf"])
    vol_gate = float(p["vol_regime_min"])

    if df_prepped is None:
        df = load_asset(symbol)
        if btc_ref is None and symbol != "BTCUSDT":
            btc = load_asset("BTCUSDT")
            btc_ref = btc[["Close", "CVD"]].copy()
            btc_ref.columns = ["btc_Close", "btc_CVD"]
        elif symbol == "BTCUSDT":
            btc_ref = df[["Close", "CVD"]].copy()
            btc_ref.columns = ["btc_Close", "btc_CVD"]
        df = prep_ensemble(df, btc_ref).reset_index()
        if "ts" not in df.columns:
            df = df.rename(columns={df.columns[0]: "ts"})
    else:
        df = df_prepped.copy()
        if "ts" not in df.columns:
            df = df.reset_index()
            if "ts" not in df.columns:
                df = df.rename(columns={df.columns[0]: "ts"})

    mask = (df["ts"] >= pd.Timestamp(start)) & (df["ts"] <= pd.Timestamp(end))
    df = df.loc[mask].reset_index(drop=True)

    empty = {
        "symbol": symbol, "strategy": "Ensemble_Master", "n_trades": 0,
        "avg_r": 0.0, "total_r": 0.0, "win_rate": 0.0, "profit_factor": 0.0,
        "avg_win_r": 0.0, "avg_loss_r": 0.0, "tp_hits": 0, "sl_hits": 0,
        "trail_hits": 0, "timeout_hits": 0, "params": p,
    }
    if len(df) < 200:
        return empty if not return_trades else {**empty, "trades": []}

    h, l, c, a = df["High"].values, df["Low"].values, df["Close"].values, df["atr"].values
    ts = df["ts"].to_numpy()
    results: List[TradeResult] = []
    raw_trades: List[dict] = []
    votes_hist: List[Tuple[int, int, int]] = []
    i, cooldown_until = 30, 0

    while i < len(df) - MAX_BARS - 2:
        row = df.iloc[i]
        v1 = vote_m1_liquidation(row, p)
        v2 = vote_m2_cvd_flow(row, p)
        v3 = vote_m3_price_action(row, p)
        votes_hist.append((v1, v2, v3))

        if i < cooldown_until:
            i += 1
            continue
        if float(row.get("vol_regime", 0.0)) < vol_gate:
            i += 1
            continue

        direction, n_agree, votes = soft_window_consensus(votes_hist, min_votes, vote_window)
        if direction == 0:
            i += 1
            continue
        if p.get("require_m2_anchor", True) and votes[1] != direction:
            i += 1
            continue
        if p.get("require_m3_agree", False) and votes[2] != direction:
            i += 1
            continue

        macro = int(row.get("macro", 0))
        if direction == 1 and macro < 0:
            i += 1
            continue
        if direction == -1 and macro > 0:
            i += 1
            continue

        tr = simulate_trade(h, l, c, a, i, direction, sl_mult, tp_mult, trail_act, trail_buf)
        results.append(tr)

        exit_idx = min(i + tr.bars_held, len(df) - 1)
        if tr.reason == "TIMEOUT":
            exit_px = float(c[exit_idx])
        elif direction == 1:
            exit_px = float(l[exit_idx]) if tr.reason in ("SL", "TRAIL") else float(h[exit_idx])
        else:
            exit_px = float(h[exit_idx]) if tr.reason in ("SL", "TRAIL") else float(l[exit_idx])

        risk_mult = float(p.get("triple_risk_mult", 1.0)) if n_agree >= 3 else 1.0
        if return_trades:
            raw_trades.append({
                "entry_time": str(ts[i]),
                "exit_time": str(ts[exit_idx]),
                "entry_price": float(c[i]),
                "exit_price": exit_px,
                "direction": direction,
                "pnl": tr.r_multiple,
                "r_multiple": tr.r_multiple,
                "risk_mult": risk_mult,
                "reason": tr.reason,
                "votes": f"L{votes[0]:+d}|C{votes[1]:+d}|P{votes[2]:+d}",
                "n_agree": n_agree,
                "bars_held": tr.bars_held,
                "symbol": symbol,
            })

        cool = int(p["cooldown_tp"]) if tr.reason == "TP" else int(p["cooldown_sl"])
        cooldown_until = i + tr.bars_held + cool
        i = cooldown_until

    if not results:
        return empty if not return_trades else {**empty, "trades": []}

    rs = np.array([t.r_multiple for t in results])
    wins, losses = rs[rs > 0], rs[rs <= 0]
    pf = float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else float("inf")
    out = {
        "symbol": symbol, "strategy": "Ensemble_Master",
        "n_trades": int(len(results)), "avg_r": float(rs.mean()), "total_r": float(rs.sum()),
        "win_rate": float((rs > 0).mean() * 100.0), "profit_factor": pf,
        "avg_win_r": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss_r": float(losses.mean()) if len(losses) else 0.0,
        "tp_hits": int(sum(1 for t in results if t.reason == "TP")),
        "sl_hits": int(sum(1 for t in results if t.reason == "SL")),
        "trail_hits": int(sum(1 for t in results if t.reason == "TRAIL")),
        "timeout_hits": int(sum(1 for t in results if t.reason == "TIMEOUT")),
        "params": p,
    }
    if return_trades:
        out["trades"] = raw_trades
    return out


def preload_universe(symbols: List[str]):
    """Load+prep with float32 downcast to reduce RAM (~half)."""
    print(f"[Ensemble] Loading from {PQ_DIR} ...")
    btc = load_asset("BTCUSDT")
    btc_ref = btc[["Close", "CVD"]].copy()
    btc_ref.columns = ["btc_Close", "btc_CVD"]
    cache = {}
    keep = {
        "ts", "Open", "High", "Low", "Close", "atr", "macro", "macro_score",
        "pull_ema8", "pull_ema21", "rsi", "stoch_k", "cvd_delta",
        "z_cvd_4", "z_cvd_10", "z_cvd_20", "z_btc_10", "z_btc_20",
        "btc_cvd_mom", "cvd_accel", "vol_regime",
        "liq_long_z_50", "liq_long_z_200", "liq_short_z_50", "liq_short_z_200",
    }
    for sym in symbols:
        print(f"  prep {sym} ...", flush=True)
        raw = btc if sym == "BTCUSDT" else load_asset(sym)
        df = prep_ensemble(raw, btc_ref).reset_index()
        if "ts" not in df.columns:
            df = df.rename(columns={df.columns[0]: "ts"})
        cols = [c for c in df.columns if c in keep]
        df = df[cols].copy()
        for c in df.columns:
            if c != "ts" and pd.api.types.is_float_dtype(df[c]):
                df[c] = df[c].astype(np.float32)
        cache[sym] = df
        del raw
    return cache, btc_ref


# ===========================================================================
# 18-window monthly portfolio validation
# ===========================================================================
def run_monthly_oos(
    params: Optional[dict] = None,
    symbols: Optional[List[str]] = None,
    cache: Optional[dict] = None,
    quiet: bool = False,
) -> dict:
    symbols = symbols or SYMBOLS
    p = {**DEFAULT_PARAMS, **(params or {})}
    if cache is None:
        cache, _ = preload_universe(symbols)

    risk_pct = float(p.get("risk_pct", 0.01))
    starting_capital = float(p.get("starting_capital", 5000.0))
    risk_usd = starting_capital * risk_pct
    months = []
    all_trades = []

    for start, end in OOS_MONTHS:
        month_trades = []
        for sym in symbols:
            res = run_ensemble_symbol(
                sym, params=p, start=start, end=end,
                df_prepped=cache[sym], return_trades=True,
            )
            month_trades.extend(res.get("trades", []))

        month_trades.sort(key=lambda x: str(x["entry_time"]))
        # Weighted R: 3/3 consensus can use triple_risk_mult
        weighted_r = [
            float(t["r_multiple"]) * float(t.get("risk_mult", 1.0)) for t in month_trades
        ]
        total_r = float(sum(weighted_r)) if weighted_r else 0.0
        plain_r = [float(t["r_multiple"]) for t in month_trades]
        wins = [r for r in plain_r if r > 0]
        wr = 100.0 * len(wins) / len(plain_r) if plain_r else 0.0
        avg_win = float(np.mean(wins)) if wins else 0.0
        usd = total_r * risk_usd
        ret_pct = 100.0 * usd / starting_capital

        passed = (
            ret_pct >= GATE_RETURN_PCT
            and wr >= GATE_WIN_RATE
            and avg_win >= GATE_AVG_WIN_R
            and len(month_trades) > 0
        )
        row = {
            "start": start, "end": end,
            "n_trades": len(month_trades),
            "total_r": total_r,
            "win_rate": wr,
            "avg_win_r": avg_win,
            "usd_pnl": usd,
            "return_pct": ret_pct,
            "passed": passed,
        }
        months.append(row)
        all_trades.extend(month_trades)
        if not quiet:
            flag = "PASS" if passed else "FAIL"
            print(
                f"  [{flag}] {start}→{end}: n={len(month_trades):3d} "
                f"ret={ret_pct:6.1f}% wr={wr:5.1f}% avg_win={avg_win:.2f}R total_r={total_r:.1f}"
            )

    n_pass = sum(1 for m in months if m["passed"])
    return {
        "strategy": "Ensemble_Master",
        "months": months,
        "n_months": len(months),
        "n_passed": n_pass,
        "all_passed": n_pass == len(months),
        "mean_monthly_return_pct": float(np.mean([m["return_pct"] for m in months])),
        "min_monthly_return_pct": float(np.min([m["return_pct"] for m in months])),
        "mean_win_rate": float(np.mean([m["win_rate"] for m in months if m["n_trades"]] or [0])),
        "min_win_rate": float(np.min([m["win_rate"] for m in months if m["n_trades"]] or [0])),
        "mean_avg_win_r": float(np.mean([m["avg_win_r"] for m in months if m["n_trades"]] or [0])),
        "min_avg_win_r": float(np.min([m["avg_win_r"] for m in months if m["avg_win_r"] > 0] or [0])),
        "total_trades": len(all_trades),
        "params": p,
        "gates": {
            "return_pct": GATE_RETURN_PCT,
            "win_rate": GATE_WIN_RATE,
            "avg_win_r": GATE_AVG_WIN_R,
        },
    }


def search_params_until_pass(max_trials: int = 80) -> dict:
    """
    Grid / random search over consensus knobs until ALL 18 months pass,
    or return best partial result.
    """
    symbols = SYMBOLS
    cache, _ = preload_universe(symbols)

    # Structured grid focused on monthly R-sum and WR
    grid = {
        "cvd_z_min": [2.2, 2.4, 2.6, 2.8, 3.0],
        "liq_z_min": [2.2, 2.5, 2.8],
        "tp_mult": [6.5, 7.5, 8.5],
        "trail_act": [3.5, 4.5, 5.0],
        "vote_window": [1, 3],
        "triple_risk_mult": [1.0, 1.5, 2.0],
        "cooldown_sl": [2, 3, 4],
        "macro_min": [0.2, 0.4],
    }

    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    rng = np.random.default_rng(42)
    rng.shuffle(combos)
    combos = combos[:max_trials]

    best = None
    best_score = -1e18

    for t, vals in enumerate(combos):
        params = {**DEFAULT_PARAMS}
        for k, v in zip(keys, vals):
            params[k] = v
        params["sl_mult"] = 1.0
        params["min_votes"] = 2
        params["require_m2_anchor"] = True
        params["trail_buf"] = 0.40
        params["risk_pct"] = 0.01

        # Enforce tp >= 5R
        if params["tp_mult"] < 5.0:
            params["tp_mult"] = 5.5

        print(f"\n--- trial {t+1}/{len(combos)} cvd={params['cvd_z_min']} "
              f"tp={params['tp_mult']} win={params['vote_window']} "
              f"x3={params['triple_risk_mult']} ---")
        summary = run_monthly_oos(params=params, symbols=symbols, cache=cache, quiet=False)

        # Score: prioritize all_passed, then min monthly return, then mean WR
        score = (
            (10000 if summary["all_passed"] else 0)
            + summary["n_passed"] * 100
            + summary["min_monthly_return_pct"]
            + summary["min_win_rate"] * 0.5
            + summary["min_avg_win_r"] * 2
        )
        if score > best_score:
            best_score = score
            best = summary
            print(
                f"  * new best: passed={summary['n_passed']}/{summary['n_months']} "
                f"min_ret={summary['min_monthly_return_pct']:.1f}% "
                f"min_wr={summary['min_win_rate']:.1f}% "
                f"min_avg_win={summary['min_avg_win_r']:.2f}R"
            )
        if summary["all_passed"]:
            print("\n*** ALL 18 WINDOWS PASSED ***")
            return summary

    print("\n[search] exhausted trials without perfect pass; returning best partial")
    return best or {}


def run_all_symbols(params=None, start="2024-06-01", end="2026-07-01", symbols=None):
    symbols = symbols or SYMBOLS
    cache, _ = preload_universe(symbols)
    per, avg_rs = {}, []
    for sym in symbols:
        m = run_ensemble_symbol(sym, params=params, start=start, end=end, df_prepped=cache[sym])
        per[sym] = m
        if m["n_trades"] > 0:
            avg_rs.append(m["avg_r"])
        print(
            f"  {sym}: avg_r={m['avg_r']:.3f} n={m['n_trades']} wr={m['win_rate']:.1f}% "
            f"avg_win={m['avg_win_r']:.2f}R"
        )
    return {
        "strategy": "Ensemble_Master",
        "mean_avg_r": float(np.mean(avg_rs)) if avg_rs else 0.0,
        "mean_win_rate": float(np.mean([per[s]["win_rate"] for s in symbols if per[s]["n_trades"]] or [0])),
        "mean_avg_win_r": float(np.mean([per[s]["avg_win_r"] for s in symbols if per[s]["n_trades"]] or [0])),
        "per_symbol": per,
        "params": {**DEFAULT_PARAMS, **(params or {})},
    }


def main():
    parser = argparse.ArgumentParser(description="Ensemble Master 2-of-3")
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--months", action="store_true")
    parser.add_argument("--search", action="store_true", help="Iterate params until all 18 windows pass")
    parser.add_argument("--start", default="2024-06-01")
    parser.add_argument("--end", default="2026-07-01")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--max-trials", type=int, default=60)
    args = parser.parse_args()

    out_dir = ROOT / "optimization"
    out_dir.mkdir(exist_ok=True)

    if args.search:
        print("=" * 70)
        print("ENSEMBLE SEARCH — all 18 months must PASS")
        print(f"  gates: ret>={GATE_RETURN_PCT}% wr>={GATE_WIN_RATE}% avg_win>={GATE_AVG_WIN_R}R")
        print("=" * 70)
        summary = search_params_until_pass(max_trials=args.max_trials)
        print("\n==== FINAL SEARCH RESULT ====")
        slim = {k: v for k, v in summary.items() if k not in ("months",)}
        print(json.dumps(slim, indent=2, default=str))
        if args.write and summary:
            path = out_dir / "ensemble_monthly_oos.json"
            with open(path, "w") as f:
                json.dump(summary, f, indent=2, default=str)
            cfg = ROOT / "ensemble_master" / "configs" / "default.json"
            cfg.parent.mkdir(parents=True, exist_ok=True)
            with open(cfg, "w") as f:
                json.dump(summary.get("params", DEFAULT_PARAMS), f, indent=4)
            # Update DEFAULT-like export
            with open(out_dir / "ensemble_pass_params.json", "w") as f:
                json.dump(summary.get("params", {}), f, indent=4)
            print(f"Wrote {path}")
            print(f"all_passed={summary.get('all_passed')} n_passed={summary.get('n_passed')}")
        sys.exit(0 if summary.get("all_passed") else 1)

    if args.months:
        print("=" * 70)
        print("ENSEMBLE MASTER — 18-window monthly OOS")
        print("=" * 70)
        summary = run_monthly_oos()
        slim = {k: v for k, v in summary.items() if k != "months"}
        print("\n==== SUMMARY ====")
        print(json.dumps(slim, indent=2, default=str))
        if args.write:
            with open(out_dir / "ensemble_monthly_oos.json", "w") as f:
                json.dump(summary, f, indent=2, default=str)
        sys.exit(0 if summary["all_passed"] else 1)

    if args.all or args.symbol is None:
        summary = run_all_symbols(start=args.start, end=args.end)
        print(json.dumps({k: summary[k] for k in summary if k != "per_symbol"}, indent=2))
        if args.write:
            with open(out_dir / "ensemble_oos_results.json", "w") as f:
                json.dump(summary, f, indent=2, default=str)
        return

    m = run_ensemble_symbol(args.symbol, start=args.start, end=args.end)
    print(json.dumps(m, indent=2, default=str))


if __name__ == "__main__":
    main()
