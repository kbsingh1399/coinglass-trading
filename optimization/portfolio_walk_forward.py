#!/usr/bin/env python3
"""Strict expanding walk-forward portfolio backtest for the three strategies.

This is intentionally a separate validator from the older single-strategy
optimizers in this repository.  It models the requested experiment directly:

* all available assets are evaluated for every window for which they have data;
* Alpha Squeezer, ML_liquidation and Trend Pull are independent sleeves running
  at the same time;
* each sleeve risks exactly $50 per entry from a $5,000 window account;
* every entry has a 1 ATR stop and a 5 ATR target;
* 0.10% total round-trip execution friction is applied as 0.05% adverse
  slippage on entry and exit;
* the account is reset to $5,000 at the beginning of each OOS window;
* each window's model is trained and its filter profile is selected using only
  bars strictly before that window.  No pre-trained model/configuration from
  a later date is loaded.

The historical training label is a conservative 5R barrier label.  The model
is a small, causal logistic model fitted separately per asset and sleeve.  A
chronological historical validation slice recursively tightens the signal
filters when it fails the requested historical gates.  Crucially, the OOS
metrics are never used to select a model, threshold, or filter.

Run from the repository root:

    python scripts/download_backtesting_data.py
    python optimization/portfolio_walk_forward.py

The JSON and Markdown reports are written below ``optimization/``.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import log_loss
    from sklearn.preprocessing import StandardScaler
except ImportError as exc:  # pragma: no cover - gives a useful CLI error
    raise SystemExit("Install pandas, pyarrow, numpy and scikit-learn before running this validator") from exc

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "backtesting_data"

# The universe is derived from the downloaded files, but this order keeps
# reports stable.  XAU/XAG are included when their limited history covers a
# window; they correctly have no observations in earlier windows.
ASSET_ORDER = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "ADAUSDT", "TRXUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT", "LTCUSDT",
    "NEARUSDT", "SUIUSDT", "XAGUSDT", "XAUUSDT",
]
STRATEGIES = ("Alpha Squeezer", "ML_liquidation", "Trend Pull")
WINDOWS = [
    ("2020-03-18", "2020-04-18"),
    ("2020-11-07", "2020-12-07"),
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

STARTING_CAPITAL = 5_000.0
RISK_PER_TRADE = 50.0
RISK_PCT = RISK_PER_TRADE / STARTING_CAPITAL
INDIVIDUAL_PROFIT_LOCK = 1_000.0  # stop a sleeve after its +20% target is reached
COMBINED_PROFIT_LOCK = 3_000.0     # stop the account after its +60% target is reached
SL_ATR = 1.0
TP_ATR = 5.0
ROUNDTRIP_FRICTION = 0.001  # 0.10% total; half is charged at each side
MAX_HOLD_BARS = 96           # 24 hours on 15-minute bars
MIN_TRAIN_BARS = 1_000
VALIDATION_BARS = 30 * 24 * 4


@dataclass(frozen=True)
class Profile:
    """A monotonically stricter filter profile."""

    name: str
    probability_min: float
    flow_min: float
    macro_min: float
    liquidation_z_min: float


# Profiles are deliberately ordered from permissive to strict.  Moving to the
# next profile is the recursive tightening step; the OOS result is never read
# in this loop.
PROFILES = {
    "Alpha Squeezer": [
        Profile("A0", .48, .45, .00, 0.0),
        Profile("A1", .52, .80, .10, 0.0),
        Profile("A2", .56, 1.20, .20, 0.0),
        Profile("A3", .60, 1.65, .30, 0.0),
        Profile("A4", .64, 2.10, .45, 0.0),
    ],
    "Trend Pull": [
        Profile("T0", .48, .25, .00, 0.0),
        Profile("T1", .52, .55, .08, 0.0),
        Profile("T2", .56, .90, .16, 0.0),
        Profile("T3", .60, 1.30, .25, 0.0),
        Profile("T4", .64, 1.75, .35, 0.0),
    ],
    "ML_liquidation": [
        Profile("L0", .48, -.50, -2.0, 1.50),
        Profile("L1", .52, -.25, -1.0, 2.00),
        Profile("L2", .56, .00, -.25, 2.50),
        Profile("L3", .60, .35, .00, 3.00),
        Profile("L4", .64, .70, .15, 3.50),
    ],
}

FEATURES = [
    "ret_4", "ret_16", "macro_score", "pull_8", "pull_21", "rsi",
    "z_cvd_4", "z_cvd_20", "z_cvd_50", "cvd_impulse", "vol_z",
    "liq_long_z_200", "liq_short_z_200", "funding_z", "oi_z",
]


def _zscore(series: pd.Series, window: int) -> pd.Series:
    min_periods = min(window, max(5, min(window, 20)))
    mean = series.rolling(window, min_periods=min_periods).mean()
    std = series.rolling(window, min_periods=min_periods).std()
    return (series - mean) / std.replace(0.0, np.nan)


def _first_present(columns: Iterable[str], choices: Sequence[str]) -> Optional[str]:
    available = set(columns)
    return next((c for c in choices if c in available), None)


def load_summary(symbol: str, data_dir: Path) -> pd.DataFrame:
    path = data_dir / f"Master_{symbol}_15m_Final_Summary.parquet"
    if not path.exists():
        # Keep the loader useful with the alternate naming used by older data
        # snapshots, without ever silently using a different data directory.
        path = data_dir / f"{symbol}_15m_summary.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    raw = pd.read_parquet(path)
    ts_col = _first_present(raw.columns, ("TimeStamp", "Timestamp", "time"))
    if ts_col is None:
        raise ValueError(f"{path} has no timestamp column")
    ts = raw[ts_col].astype(str).str.replace(" IST", "", regex=False)
    raw["ts"] = pd.to_datetime(ts, errors="coerce")
    raw = raw.dropna(subset=["ts"]).sort_values("ts").drop_duplicates("ts")
    numeric = [c for c in raw.columns if c not in {"ts", ts_col, "Symbol"}]
    for col in numeric:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    return raw.set_index("ts")


def prepare_features(df: pd.DataFrame, btc: Optional[pd.DataFrame]) -> pd.DataFrame:
    """Compute only backward-looking features.

    ``rolling`` and ``ewm`` values at row *t* use row *t* and earlier only.
    The BTC reference is reindexed and forward-filled, which is also causal
    for assets whose bars are not exactly synchronized with BTC.
    """
    out = df.copy()
    for col in ("Open", "High", "Low", "Close", "Volume", "CVD"):
        if col not in out:
            out[col] = 0.0
    if btc is not None and "CVD" in btc:
        btc_cvd = btc["CVD"].reindex(out.index).ffill().fillna(0.0)
    else:
        btc_cvd = pd.Series(0.0, index=out.index)
    out["btc_cvd"] = btc_cvd.to_numpy()

    close = out["Close"].astype(float)
    high = out["High"].astype(float)
    low = out["Low"].astype(float)
    prev_close = close.shift(1).fillna(close)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    out["atr"] = tr.rolling(14, min_periods=14).mean()
    atr = out["atr"].replace(0.0, np.nan)

    for period, name in ((4, "ret_4"), (16, "ret_16")):
        out[name] = close.pct_change(period)
    ema8 = close.ewm(span=8, adjust=False, min_periods=8).mean()
    ema21 = close.ewm(span=21, adjust=False, min_periods=21).mean()
    ema200 = close.ewm(span=200, adjust=False, min_periods=200).mean()
    out["pull_8"] = (close - ema8) / atr
    out["pull_21"] = (close - ema21) / atr
    out["macro_score"] = (ema200 - ema200.shift(32)) / atr

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=14).mean()
    out["rsi"] = 100.0 - 100.0 / (1.0 + gain / loss.replace(0.0, np.nan))

    cvd = pd.to_numeric(out["CVD"], errors="coerce").ffill().fillna(0.0)
    for period, name in ((4, "z_cvd_4"), (20, "z_cvd_20"), (50, "z_cvd_50")):
        out[name] = _zscore(cvd, period)
    out["cvd_impulse"] = _zscore(cvd.diff(4), 50)
    out["vol_z"] = _zscore(atr, 100)

    for raw_col, name in (("Agg. Liq Long", "liq_long_z_200"), ("Agg. Liq Short", "liq_short_z_200")):
        series = pd.to_numeric(out.get(raw_col, pd.Series(0.0, index=out.index)), errors="coerce").fillna(0.0)
        mu = series.rolling(200, min_periods=20).mean()
        sd = series.rolling(200, min_periods=20).std().replace(0.0, np.nan)
        out[name] = (series - mu) / sd
    funding = pd.to_numeric(out.get("Agg. Funding Rate", pd.Series(0.0, index=out.index)), errors="coerce").fillna(0.0)
    oi = pd.to_numeric(out.get("Agg. OI", pd.Series(0.0, index=out.index)), errors="coerce").ffill().fillna(0.0)
    out["funding_z"] = _zscore(funding, 100)
    out["oi_z"] = _zscore(oi, 100)
    out[FEATURES + ["atr"]] = out[FEATURES + ["atr"]].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return out


def _future_extrema(values: np.ndarray, horizon: int, fn: str) -> np.ndarray:
    # At i this is the extrema of i+1 ... i+horizon.  The shift ordering is
    # important: no current bar is included in the training label.
    s = pd.Series(values)
    shifted = s.shift(-1)
    rolled = getattr(shifted.rolling(horizon, min_periods=horizon), fn)()
    return rolled.shift(-(horizon - 1)).to_numpy(dtype=float)


def barrier_labels(df: pd.DataFrame, direction: int, limit: int) -> Tuple[np.ndarray, np.ndarray]:
    """Return valid training indices and conservative 5R barrier labels.

    The final MAX_HOLD_BARS before ``limit`` are excluded, so even the label
    construction cannot inspect a bar from the OOS window.
    """
    n = len(df)
    high = df["High"].to_numpy(float)
    low = df["Low"].to_numpy(float)
    entry = df["Open"].shift(-1).to_numpy(float)
    atr = df["atr"].to_numpy(float)
    fh = _future_extrema(high, MAX_HOLD_BARS, "max")
    fl = _future_extrema(low, MAX_HOLD_BARS, "min")
    valid = np.arange(n)
    valid = valid[(valid + MAX_HOLD_BARS + 1 < limit) & np.isfinite(entry) & (atr > 0)]
    if direction == 1:
        tp = entry + TP_ATR * atr
        sl = entry - SL_ATR * atr
        y = ((fh >= tp) & (fl > sl)).astype(int)
    else:
        tp = entry - TP_ATR * atr
        sl = entry + SL_ATR * atr
        y = ((fl <= tp) & (fh < sl)).astype(int)
    return valid, y


@dataclass
class DirectionModel:
    scaler: Optional[StandardScaler]
    model: Optional[LogisticRegression]
    fallback: float
    selected_c: float

    def predict(self, x: np.ndarray) -> np.ndarray:
        if self.model is None or self.scaler is None:
            return np.full(len(x), self.fallback, dtype=float)
        return self.model.predict_proba(self.scaler.transform(x))[:, 1]


def _fit_direction(x: np.ndarray, y: np.ndarray) -> DirectionModel:
    if len(y) < 120 or len(np.unique(y)) < 2:
        return DirectionModel(None, None, float(np.mean(y)) if len(y) else 0.5, 0.0)
    # Chronological validation is entirely inside the historical prefix.
    split = max(60, int(len(y) * 0.75))
    split = min(split, len(y) - 20)
    candidates = (0.1, 1.0, 10.0)
    best_c, best_loss = 1.0, math.inf
    for c in candidates:
        scaler = StandardScaler().fit(x[:split])
        model = LogisticRegression(C=c, class_weight="balanced", max_iter=120, solver="liblinear")
        model.fit(scaler.transform(x[:split]), y[:split])
        if len(np.unique(y[split:])) > 1:
            loss = log_loss(y[split:], model.predict_proba(scaler.transform(x[split:])), labels=[0, 1])
        else:
            loss = float(np.mean((model.predict_proba(scaler.transform(x[split:]))[:, 1] - y[split:]) ** 2))
        if loss < best_loss:
            best_loss, best_c = loss, c
    scaler = StandardScaler().fit(x)
    model = LogisticRegression(C=best_c, class_weight="balanced", max_iter=160, solver="liblinear")
    model.fit(scaler.transform(x), y)
    return DirectionModel(scaler, model, float(np.mean(y)), best_c)


def fit_models(df: pd.DataFrame, strategy: str, cutoff: int) -> Dict[int, DirectionModel]:
    """Fit both directions using only ``df.iloc[:cutoff]``."""
    models: Dict[int, DirectionModel] = {}
    for direction in (1, -1):
        valid, y_all = barrier_labels(df, direction, cutoff)
        # Keep fitting bounded and deterministic while retaining the full
        # expanding prefix through evenly spaced historical samples.
        if len(valid) > 8_000:
            valid = valid[np.linspace(0, len(valid) - 1, 8_000, dtype=int)]
        x = df.iloc[valid][FEATURES].to_numpy(dtype=float)
        y = y_all[valid]
        models[direction] = _fit_direction(x, y)
    return models


def _heuristic_probability(df: pd.DataFrame, direction: int, strategy: str) -> np.ndarray:
    signed_flow = direction * (df["z_cvd_20"] + .35 * df["z_cvd_4"] + .15 * df["cvd_impulse"])
    if strategy == "ML_liquidation":
        liq = df["liq_long_z_200"] if direction == 1 else df["liq_short_z_200"]
        raw = .45 * signed_flow + .30 * liq + .25 * direction * df["macro_score"].clip(-2, 2)
    elif strategy == "Trend Pull":
        pull = -direction * df["pull_8"]
        raw = .55 * signed_flow + .25 * direction * df["macro_score"].clip(-2, 2) + .20 * pull
    else:
        raw = .70 * signed_flow + .30 * direction * df["macro_score"].clip(-2, 2)
    return 1.0 / (1.0 + np.exp(-np.clip(raw, -8, 8)))


def signal_arrays(
    df: pd.DataFrame,
    strategy: str,
    profile: Profile,
    models: Dict[int, DirectionModel],
    start: int,
    end: int,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Create causal test signals for [start, end]."""
    n = len(df)
    directions = np.zeros(n, dtype=np.int8)
    probability = np.zeros(n, dtype=float)
    # Predict only on the requested slice.  This both keeps the full-history
    # frame out of the hot loop and makes the causal boundary explicit.
    view = df.iloc[start:end + 1]
    signed_flow_long = view["z_cvd_20"] + .35 * view["z_cvd_4"] + .15 * view["cvd_impulse"]
    signed_flow_short = -signed_flow_long
    macro = view["macro_score"]
    if strategy == "ML_liquidation":
        long_base = (view["liq_long_z_200"] >= profile.liquidation_z_min) & (signed_flow_long >= profile.flow_min)
        short_base = (view["liq_short_z_200"] >= profile.liquidation_z_min) & (signed_flow_short >= profile.flow_min)
    elif strategy == "Trend Pull":
        long_base = (macro >= profile.macro_min) & (view["pull_8"] <= .9) & (view["pull_8"] >= -2.0) & (signed_flow_long >= profile.flow_min)
        short_base = (macro <= -profile.macro_min) & (view["pull_8"] >= -.9) & (view["pull_8"] <= 2.0) & (signed_flow_short >= profile.flow_min)
    else:
        long_base = (macro >= profile.macro_min) & (signed_flow_long >= profile.flow_min)
        short_base = (macro <= -profile.macro_min) & (signed_flow_short >= profile.flow_min)

    x = view[FEATURES].to_numpy(dtype=float)
    long_p = np.where(
        long_base.to_numpy(bool),
        .65 * models[1].predict(x) + .35 * _heuristic_probability(view, 1, strategy),
        0.0,
    )
    short_p = np.where(
        short_base.to_numpy(bool),
        .65 * models[-1].predict(x) + .35 * _heuristic_probability(view, -1, strategy),
        0.0,
    )
    long_take = long_p >= profile.probability_min
    short_take = short_p >= profile.probability_min
    local_dir = np.zeros(len(view), dtype=np.int8)
    local_dir[long_take & (long_p >= short_p)] = 1
    local_dir[short_take & (short_p > long_p)] = -1
    directions[start:end + 1] = local_dir
    probability[start:end + 1] = np.maximum(long_p, short_p)
    return directions, probability, np.zeros(n, dtype=bool)


def execute_signals(
    df: pd.DataFrame,
    symbol: str,
    strategy: str,
    directions: np.ndarray,
    start: int,
    end: int,
) -> List[dict]:
    """Execute one independent sleeve, one position at a time per asset."""
    out: List[dict] = []
    opens = df["Open"].to_numpy(float)
    highs = df["High"].to_numpy(float)
    lows = df["Low"].to_numpy(float)
    closes = df["Close"].to_numpy(float)
    atr = df["atr"].to_numpy(float)
    timestamps = df.index
    i = max(start, 0)
    while i < end:
        direction = int(directions[i])
        entry_i = i + 1  # signal at close; earliest fill is next bar open
        if direction == 0 or entry_i > end or not np.isfinite(atr[i]) or atr[i] <= 0:
            i += 1
            continue
        raw_entry = opens[entry_i]
        if not np.isfinite(raw_entry) or raw_entry <= 0:
            i += 1
            continue
        half_friction = ROUNDTRIP_FRICTION / 2.0
        entry_fill = raw_entry * (1.0 + direction * half_friction)
        stop = entry_fill - direction * SL_ATR * atr[i]
        target = entry_fill + direction * TP_ATR * atr[i]
        qty = RISK_PER_TRADE / (SL_ATR * atr[i])
        exit_i, reason, raw_exit = end, "WINDOW_CLOSE", closes[end]
        for j in range(entry_i, end + 1):
            # Stop first is the conservative rule when OHLC cannot tell which
            # barrier was touched first within the candle.
            stop_hit = lows[j] <= stop if direction == 1 else highs[j] >= stop
            target_hit = highs[j] >= target if direction == 1 else lows[j] <= target
            if stop_hit:
                exit_i, reason, raw_exit = j, "SL", stop
                break
            if target_hit:
                exit_i, reason, raw_exit = j, "TP", target
                break
        exit_fill = raw_exit * (1.0 - direction * half_friction)
        pnl = (exit_fill - entry_fill) * qty * direction
        out.append({
            "symbol": symbol,
            "strategy": strategy,
            "entry_ts": str(timestamps[entry_i]),
            "exit_ts": str(timestamps[exit_i]),
            "entry_price": float(entry_fill),
            "exit_price": float(exit_fill),
            "direction": direction,
            "atr": float(atr[i]),
            "pnl": float(pnl),
            "r_multiple": float(pnl / RISK_PER_TRADE),
            "reason": reason,
            "bars_held": int(exit_i - entry_i + 1),
        })
        # No overlapping position in the same strategy/asset.  Other sleeves
        # and other assets remain concurrent on the same account.
        i = max(i + 1, exit_i + 1)
    return out


def apply_profit_lock(trades: Sequence[dict], target_pnl: float) -> List[dict]:
    """Stop a sleeve/account once its realized monthly target is reached.

    This is a forward-only risk rule: it looks only at already-realized exits
    and prevents giving back a reached target.  It does not alter entry
    selection or any OOS metric used for re-optimization.
    """
    realized = 0.0
    kept: List[dict] = []
    for trade in sorted(trades, key=lambda t: (t["exit_ts"], t["entry_ts"])):
        kept.append(trade)
        realized += float(trade["pnl"])
        if realized >= target_pnl:
            break
    return kept


def metrics(trades: Sequence[dict], combined_gate: bool = False) -> dict:
    pnl = float(sum(float(t["pnl"]) for t in trades))
    rs = np.asarray([float(t["r_multiple"]) for t in trades], dtype=float)
    wins = rs[rs > 0]
    roi = 100.0 * pnl / STARTING_CAPITAL
    roi_pass = roi >= 60.0 if combined_gate else roi > 20.0
    return {
        "n_trades": int(len(rs)),
        "wins": int(len(wins)),
        "losses": int(np.sum(rs <= 0)),
        "win_rate_pct": float(100.0 * len(wins) / len(rs)) if len(rs) else 0.0,
        "pnl_usd": pnl,
        "roi_pct": float(roi),
        "total_r": float(rs.sum()) if len(rs) else 0.0,
        "avg_r": float(rs.mean()) if len(rs) else 0.0,
        "passed": bool(len(rs) and len(wins) / len(rs) > .40 and roi_pass),
    }


def historical_profile_selection(
    df: pd.DataFrame,
    symbol: str,
    strategy: str,
    models: Dict[int, DirectionModel],
    cutoff: int,
) -> Tuple[Profile, List[dict], bool]:
    """Tighten recursively using a historical tail, never the OOS window."""
    validation_start = max(0, cutoff - VALIDATION_BARS)
    validation_end = cutoff - 2  # entry open must also remain before cutoff
    attempts: List[dict] = []
    selected = PROFILES[strategy][-1]
    historical_pass = False
    for attempt, profile in enumerate(PROFILES[strategy], 1):
        directions, _, _ = signal_arrays(df, strategy, profile, models, validation_start, validation_end)
        trades = execute_signals(df, symbol, strategy, directions, validation_start, validation_end)
        m = metrics(trades)
        row = {"attempt": attempt, "profile": asdict(profile), **m}
        attempts.append(row)
        # This pass gate is evaluated on prior data only.  If it fails, the
        # next attempt applies tighter filters before the OOS window is seen.
        if m["win_rate_pct"] > 40.0 and m["roi_pct"] > 20.0:
            selected, historical_pass = profile, True
            break
        selected = profile
    return selected, attempts, historical_pass


def _asset_files(data_dir: Path) -> List[str]:
    names = {p.name.split("Master_", 1)[-1].split("_15m_Final_Summary", 1)[0] for p in data_dir.glob("Master_*_15m_Final_Summary.parquet")}
    if not names:
        names = {p.name.split("_15m_summary", 1)[0] for p in data_dir.glob("*_15m_summary.parquet")}
    return [s for s in ASSET_ORDER if s in names] + sorted(names - set(ASSET_ORDER))


def run_backtest(data_dir: Path, selected_windows: Optional[Sequence[Tuple[str, str]]] = None, quiet: bool = False) -> dict:
    windows = list(selected_windows or WINDOWS)
    assets = _asset_files(data_dir)
    if not assets:
        raise FileNotFoundError(f"No summary parquet files found in {data_dir}")
    print(f"[data] {data_dir} | assets={len(assets)}")
    btc = load_summary("BTCUSDT", data_dir)
    asset_frames: Dict[str, pd.DataFrame] = {}
    coverage = {}
    for symbol in assets:
        raw = load_summary(symbol, data_dir)
        asset_frames[symbol] = prepare_features(raw, btc)
        coverage[symbol] = {"first": str(raw.index.min()), "last": str(raw.index.max()), "bars": len(raw)}
        print(f"  loaded {symbol}: {len(raw):,} bars {raw.index.min().date()} → {raw.index.max().date()}")

    month_trades: Dict[int, Dict[str, List[dict]]] = {
        i: {s: [] for s in STRATEGIES} for i in range(len(windows))
    }
    selection_log: Dict[str, dict] = {}
    for symbol, df in asset_frames.items():
        ts = df.index
        for wi, (start_s, end_s) in enumerate(windows, 1):
            start = int(ts.searchsorted(pd.Timestamp(start_s), side="left"))
            end = int(ts.searchsorted(pd.Timestamp(end_s), side="right") - 1)
            if start >= len(df) or end <= start or start < MIN_TRAIN_BARS:
                continue  # not enough strictly prior data for this asset/window
            for strategy in STRATEGIES:
                key = f"{wi}:{symbol}:{strategy}"
                models = fit_models(df, strategy, start)
                profile, attempts, hist_pass = historical_profile_selection(df, symbol, strategy, models, start)
                directions, _, _ = signal_arrays(df, strategy, profile, models, start, end)
                trades = execute_signals(df, symbol, strategy, directions, start, end)
                month_trades[wi - 1][strategy].extend(trades)
                selection_log[key] = {
                    "window": wi, "symbol": symbol, "strategy": strategy,
                    "oos_start": start_s, "oos_end": end_s,
                    "history_bars": start, "selected_profile": asdict(profile),
                    "historical_pass": hist_pass,
                    "tightening_attempts": attempts,
                    "long_C": models[1].selected_c, "short_C": models[-1].selected_c,
                }
            if not quiet:
                print(f"  [{symbol}] window {wi} complete ({start_s} → {end_s})", flush=True)

    windows_out = []
    for wi, (start, end) in enumerate(windows):
        by_strategy = {}
        combined: List[dict] = []
        for strategy in STRATEGIES:
            # Once an individual sleeve realizes +$1,000, it is disabled for
            # the remainder of that OOS month.  This is an implementable
            # target-lock rule, not test-result feedback.
            trades = apply_profit_lock(month_trades[wi][strategy], INDIVIDUAL_PROFIT_LOCK)
            by_strategy[strategy] = metrics(trades)
            combined.extend(trades)
        # The same account stops all sleeves once +$3,000 is realized.  The
        # order is by exit, so simultaneous positions are handled causally.
        combined = apply_profit_lock(combined, COMBINED_PROFIT_LOCK)
        cm = metrics(combined, combined_gate=True)
        windows_out.append({
            "number": wi + 1,
            "start": start,
            "end": end,
            "strategies": by_strategy,
            "combined": cm,
            "assets_with_trades": sorted({t["symbol"] for t in combined}),
        })
        print(
            f"[window {wi + 1:02d}] {start} → {end} | "
            + " | ".join(f"{s}: ${by_strategy[s]['pnl_usd']:.0f}/{by_strategy[s]['win_rate_pct']:.1f}%" for s in STRATEGIES)
            + f" | combined ${cm['pnl_usd']:.0f}/{cm['win_rate_pct']:.1f}% "
            + ("PASS" if cm["passed"] else "FAIL")
        )

    def all_pass(field: str, strategy: Optional[str] = None) -> bool:
        vals = []
        for w in windows_out:
            m = w["combined"] if strategy is None else w["strategies"][strategy]
            vals.append(bool(m["passed"]))
        return bool(vals) and all(vals)

    result = {
        "spec": {
            "starting_capital_usd": STARTING_CAPITAL,
            "risk_per_trade_usd": RISK_PER_TRADE,
            "risk_pct_initial": RISK_PCT,
            "individual_profit_lock_usd": INDIVIDUAL_PROFIT_LOCK,
            "combined_profit_lock_usd": COMBINED_PROFIT_LOCK,
            "sl_atr": SL_ATR,
            "tp_atr": TP_ATR,
            "minimum_rr": TP_ATR / SL_ATR,
            "roundtrip_friction": ROUNDTRIP_FRICTION,
            "roundtrip_friction_pct": ROUNDTRIP_FRICTION * 100.0,
            "individual_gate": "win rate > 40.0% AND ROI > 20.0%",
            "combined_gate": "win rate > 40.0% AND ROI >= 60.0%",
            "validation": "strict expanding; models and filters use only bars before each OOS start",
            "entry_timing": "signal at bar close, fill at next bar open",
            "same_account": True,
            "window_reset": True,
        },
        "data": {"directory": str(data_dir), "assets": assets, "coverage": coverage},
        "windows": windows_out,
        "selection_log": selection_log,
        "summary": {
            "n_windows": len(windows_out),
            "combined_passed": sum(bool(w["combined"]["passed"]) for w in windows_out),
            "individual_passed": {s: sum(bool(w["strategies"][s]["passed"]) for w in windows_out) for s in STRATEGIES},
            "all_combined_passed": all_pass("passed"),
            "all_individual_passed": {s: all_pass("passed", s) for s in STRATEGIES},
            "note": "A failed gate is reported as a failure; no OOS result is fed back into re-optimization.",
        },
    }
    return result


def write_report(result: dict, out_json: Path, out_md: Path) -> None:
    out_json.write_text(json.dumps(result, indent=2, default=str))
    lines = [
        "# Three-strategy strict expanding walk-forward report",
        "",
        "This report is generated from `optimization/portfolio_walk_forward.py`. "
        "The OOS metrics are not used to select parameters.",
        "",
        "## Fixed execution specification",
        "",
        "| Item | Value |",
        "|---|---:|",
        f"| Window starting capital | ${STARTING_CAPITAL:,.2f} (reset every window) |",
        f"| Risk per trade | ${RISK_PER_TRADE:,.2f} ({RISK_PCT:.1%} initial capital) |",
        f"| Profit locks | ${INDIVIDUAL_PROFIT_LOCK:,.0f} per sleeve; ${COMBINED_PROFIT_LOCK:,.0f} account |",
        f"| Stop / target | {SL_ATR:.1f} ATR / {TP_ATR:.1f} ATR ({TP_ATR / SL_ATR:.1f}R) |",
        f"| Round-trip friction | {ROUNDTRIP_FRICTION:.2%} |",
        "| Entry | next 15-minute bar open after a close signal |",
        "",
        "## Window results",
        "",
        "| # | Dates | Alpha Squeezer | ML_liquidation | Trend Pull | Combined |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for w in result["windows"]:
        def cell(m):
            return f"${m['pnl_usd']:,.0f} / {m['roi_pct']:.1f}% / {m['win_rate_pct']:.1f}% / {m['n_trades']} {'PASS' if m['passed'] else 'FAIL'}"
        lines.append("| {} | {} → {} | {} | {} | {} | {} |".format(
            w["number"], w["start"], w["end"],
            cell(w["strategies"][STRATEGIES[0]]), cell(w["strategies"][STRATEGIES[1]]),
            cell(w["strategies"][STRATEGIES[2]]), cell(w["combined"])))
    lines += [
        "",
        "Legend: each cell is `PnL / ROI / win rate / trades PASS|FAIL`; individual PASS "
        "means win rate >40% and ROI >20%, while combined PASS means win rate >40% "
        "and ROI ≥60%.",
        "",
        "## Gate summary",
        "",
        f"- Combined: **{result['summary']['combined_passed']}/{result['summary']['n_windows']}** windows passed; "
        f"all passed = **{result['summary']['all_combined_passed']}**.",
    ]
    for strategy in STRATEGIES:
        lines.append(
            f"- {strategy}: **{result['summary']['individual_passed'][strategy]}/{result['summary']['n_windows']}** "
            f"windows passed; all passed = **{result['summary']['all_individual_passed'][strategy]}**."
        )
    lines += [
        "",
        "## Reproduction",
        "",
        "```bash",
        "python scripts/download_backtesting_data.py --verify-only",
        "python optimization/portfolio_walk_forward.py",
        "```",
        "",
        "The limited-history XAUUSDT/XAGUSDT files are included when their data "
        "covers a window; earlier windows correctly have no eligible training prefix "
        "for those assets.",
    ]
    out_md.write_text("\n".join(lines) + "\n")


def parse_window_numbers(value: Optional[str]) -> Optional[List[Tuple[str, str]]]:
    if not value:
        return None
    numbers = {int(x.strip()) for x in value.split(",")}
    bad = numbers - set(range(1, len(WINDOWS) + 1))
    if bad:
        raise ValueError(f"invalid window numbers: {sorted(bad)}")
    return [WINDOWS[i - 1] for i in sorted(numbers)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--windows", help="comma-separated window numbers, useful for a smoke test")
    parser.add_argument("--out-json", type=Path, default=ROOT / "optimization" / "portfolio_walk_forward.json")
    parser.add_argument("--out-md", type=Path, default=ROOT / "optimization" / "portfolio_walk_forward_report.md")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    selected = parse_window_numbers(args.windows)
    result = run_backtest(args.data_dir.resolve(), selected, quiet=args.quiet)
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    write_report(result, args.out_json, args.out_md)
    print(f"[report] {args.out_json}")
    print(f"[report] {args.out_md}")
    print(json.dumps(result["summary"], indent=2))
    # A validator should signal a failed target without claiming success.  The
    # report remains useful and is still written in either case.
    return 0 if result["summary"]["all_combined_passed"] and all(result["summary"]["all_individual_passed"].values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
