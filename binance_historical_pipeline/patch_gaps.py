"""
patch_gaps.py  -  Fast Targeted Gap Patcher for all 15m Parquet assets.

Bypasses run_pipeline.py entirely. For each asset:
  1. Scans the master parquet for incomplete days (< expected candle count).
  2. Downloads ONLY those specific raw CSV files from Binance.
  3. Processes only the gap days inline (no year-block subprocess chains).
  4. Merges patched rows back via unique(subset=["TimeStamp"], keep="last").
  5. Recalculates Candle numbers and CVD globally and saves the master.

Usage:
  python patch_gaps.py                    # Patch all assets
  python patch_gaps.py --symbol AVAXUSDT  # Single asset
  python patch_gaps.py --dry-run          # Just report gaps, no downloads
"""

import os
import sys
import gc
import time
import glob
import shutil
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

import polars as pl
import pandas as pd
import numpy as np

# --- PATHS ---------------------------------------------------------------------
PARQUET_DIR    = r"G:\My Drive\_Trading_Data\15m\parquet"
PIPELINE_DIR   = r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\binance_historical_pipeline"
INTERVAL       = "15m"
EXPECTED_CANDLES = 96   # 24h x 4 candles/h  - days with <96 are treated as incomplete
MIN_CANDLES      = 92   # below this we redownload (accounts for any DST/maint < 4 candles short)
TYPES = ["aggTrades", "metrics", "liquidationSnapshot", "premiumIndexKlines"]
IST_OFFSET = pl.duration(hours=5, minutes=30)

# --- ASSET REGISTRY (symbol -> tick_size) ---------------------------------------
ASSETS = {
    "XAGUSDT":  0.01,
    "XAUUSDT":  0.1,
    "XRPUSDT":  0.0001,
    "ADAUSDT":  0.0001,
    "AVAXUSDT": 0.05,
    "BNBUSDT":  0.5,
    "BTCUSDT":  15.0,
    "DOGEUSDT": 0.0001,
    "DOTUSDT":  0.01,
    "ETHUSDT":  1.0,
    "LINKUSDT": 0.01,
    "LTCUSDT":  0.1,
    "NEARUSDT": 0.001,
    "SOLUSDT":  0.1,
    "SUIUSDT":  0.001,
    "TRXUSDT":  0.0001,
}

IGNORED_GAPS_FILE = os.path.join(PIPELINE_DIR, "ignored_gaps.txt")

def get_master_path(symbol):
    return os.path.join(PARQUET_DIR, f"Master_{symbol}_{INTERVAL}_Final_Summary.parquet")

def get_year_path(symbol, year):
    base = get_master_path(symbol)
    return base.replace(".parquet", f"_{year}.parquet")

def safe_write(df: pl.DataFrame, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    for attempt in range(8):
        try:
            df.write_parquet(tmp)
            os.replace(tmp, path)
            return True
        except PermissionError:
            print(f"  [LOCK] G-Drive lock on {os.path.basename(path)}, retry {attempt+1}/8...")
            time.sleep(2)
        except Exception as e:
            print(f"  [ERR] Write failed: {e}")
            if os.path.exists(tmp):
                os.remove(tmp)
            return False
    return False

# --- IGNORED GAPS PERSISTENCE ---------------------------------------------------
def _load_ignored_gaps(symbol: str) -> set[str]:
    """Load the set of date-strings that are known Binance maintenance/short days for this symbol."""
    ignored = set()
    if os.path.exists(IGNORED_GAPS_FILE):
        with open(IGNORED_GAPS_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",", 1)
                if len(parts) == 2 and parts[0] == symbol:
                    ignored.add(parts[1])
    return ignored

def _save_ignored_gaps(symbol: str, dates: list[str]):
    """Append dates to the ignored-gaps ledger."""
    with open(IGNORED_GAPS_FILE, "a") as f:
        for d in dates:
            f.write(f"{symbol},{d}\n")

# --- GAP DETECTION --------------------------------------------------------------
def detect_gaps(symbol: str) -> list[str]:
    """Return sorted list of YYYY-MM-DD strings that are missing or incomplete in
    either Summary or Footprint, excluding the launch day, today, and known
    Binance maintenance days."""
    master = get_master_path(symbol)
    fp_master = master.replace("Summary", "Footprint")

    ignored = _load_ignored_gaps(symbol)
    today_str = datetime.now().strftime("%Y-%m-%d")

    missing_dates = set()
    for p, t_col in [(master, "TimeStamp"), (fp_master, "Timestamp")]:
        if not os.path.exists(p):
            continue
        s = pl.read_parquet(p, columns=[t_col])[t_col]
        date_col = s.str.slice(0, 10)

        # Per-day row counts already in the file
        counts = pl.DataFrame({"date": date_col}).group_by("date").len()
        counts_dict = dict(zip(counts["date"].to_list(), counts["len"].to_list()))

        min_date = date_col.min()
        if not min_date:
            continue

        # Walk the full calendar from first day → yesterday
        start_dt = datetime.strptime(min_date, "%Y-%m-%d")
        yesterday_dt = datetime.now() - timedelta(days=1)

        cur = start_dt
        while cur <= yesterday_dt:
            d_str = cur.strftime("%Y-%m-%d")
            row_count = counts_dict.get(d_str, 0)
            if row_count < MIN_CANDLES:
                # Skip: launch day, today, and known maintenance days
                if d_str != min_date and d_str != today_str and d_str not in ignored:
                    missing_dates.add(d_str)
            cur += timedelta(days=1)

    return sorted(missing_dates)

def detect_new_dates(symbol: str) -> list[str]:
    """Return list of date strings from (oldest last parquet date + 1) up to yesterday."""
    master = get_master_path(symbol)
    fp_master = master.replace("Summary", "Footprint")

    last_dates = []
    for p, t_col in [(master, "TimeStamp"), (fp_master, "Timestamp")]:
        if os.path.exists(p):
            s = pl.read_parquet(p, columns=[t_col])[t_col]
            last_dates.append(s.str.slice(0, 10).max())

    if not last_dates:
        return []

    # Take the MINIMUM of the max dates so we don't leave either file behind
    oldest_max_date_str = min(last_dates)
    last_date = datetime.strptime(oldest_max_date_str, "%Y-%m-%d")

    # Download up to yesterday — today's candle is still building
    yesterday = datetime.now() - timedelta(days=1)
    new_dates = []
    cur = last_date + timedelta(days=1)
    while cur <= yesterday:
        new_dates.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return new_dates

def load_consolidate_engine(symbol: str, tick_size: float):
    """Import consolidate_data with the correct globals set."""
    if PIPELINE_DIR not in sys.path:
        sys.path.insert(0, PIPELINE_DIR)

    # Force reimport to reset globals cleanly
    for mod_name in ("consolidate_data", "bulk_downloader"):
        if mod_name in sys.modules:
            del sys.modules[mod_name]

    # Set cwd so relative download paths resolve
    orig_cwd = os.getcwd()
    os.chdir(PIPELINE_DIR)

    import consolidate_data as cd
    import bulk_downloader as bd

    # Patch globals
    cd.SYMBOL    = symbol
    cd.TICK_SIZE = tick_size
    cd.INTERVAL  = INTERVAL
    cd.DOWNLOADS = os.path.join(PIPELINE_DIR, "downloads")
    cd.BASE_SUMMARY_PARQUET   = get_master_path(symbol)
    cd.BASE_FOOTPRINT_PARQUET = get_master_path(symbol).replace("Summary", "Footprint")

    os.chdir(orig_cwd)
    return cd, bd

def download_gap_days(bd, symbol: str, gap_dates: list[str]):
    """Download raw CSVs for all gap dates using parallel threads."""
    print(f"  Downloading {len(gap_dates)} gap day(s) for {symbol}...")
    orig_cwd = os.getcwd()
    os.chdir(PIPELINE_DIR)
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {d: ex.submit(bd.download_day, symbol, d, TYPES, INTERVAL) for d in gap_dates}
        for d, f in futs.items():
            try:
                f.result()
                print(f"    [{symbol}] {d} - downloaded OK")
            except Exception as e:
                print(f"    [{symbol}] {d} - download WARN: {e}")
    os.chdir(orig_cwd)

def process_gap_days(cd, symbol: str, tick_size: float, gap_dates: list[str]):
    """Process each gap date through the consolidate engine and return (summary_dfs, footprint_dfs)."""
    orig_cwd = os.getcwd()
    os.chdir(PIPELINE_DIR)

    summary_results = []
    footprint_results = []
    empty_dates = []   # Track dates that Binance genuinely has no data for
    for d in gap_dates:
        try:
            summary, fp = cd.process_day(d)
            if summary is not None and not summary.empty and fp is not None and not fp.empty:
                summary["Symbol"] = symbol
                summary_results.append(summary)
                footprint_results.append(fp)
                print(f"    [{symbol}] {d} - {len(summary)} candles processed")
            else:
                empty_dates.append(d)
                print(f"    [{symbol}] {d} - no data (Binance 404 or empty)")
        except Exception as e:
            empty_dates.append(d)
            print(f"    [{symbol}] {d} - processing error: {e}")

    os.chdir(orig_cwd)
    return summary_results, footprint_results, empty_dates

def rebuild_cvd_and_candles(df: pl.DataFrame, is_footprint: bool = False) -> pl.DataFrame:
    """Recalculate Candle numbers and CVD globally after merging gap rows."""
    time_col = "Timestamp" if is_footprint else "TimeStamp"
    candle_col = "Candle #" if is_footprint else "Candle"

    df = df.sort(time_col)
    # Re-number candles
    df = df.with_columns(pl.Series(candle_col, range(1, len(df) + 1)))
    # Recompute CVD as cumsum of Candle Delta
    if not is_footprint and "Candle Delta" in df.columns:
        df = df.with_columns(
            pl.col("Candle Delta").cast(pl.Float64).fill_null(0.0).cum_sum().alias("CVD")
        )
    return df

def patch_asset(symbol: str, tick_size: float, dry_run: bool = False) -> bool:
    print(f"\n{'='*60}")

    gap_dates = detect_gaps(symbol)
    new_dates = detect_new_dates(symbol)

    # Merge both lists, deduplicate, sort
    all_dates = sorted(set(gap_dates) | set(new_dates))

    if gap_dates:
        print(f"  [{symbol}] Gaps:   {len(gap_dates)} day(s) — {gap_dates[0]} to {gap_dates[-1]}")
    if new_dates:
        print(f"  [{symbol}] New:    {len(new_dates)} day(s) since last update ({new_dates[0]} to {new_dates[-1]})")
    if not all_dates:
        print(f"  [{symbol}] OK Already up-to-date. Nothing to do.")
        return True

    if dry_run:
        return True

    # Load engine
    cd, bd = load_consolidate_engine(symbol, tick_size)

    # Download all dates (gaps + new) in parallel
    download_gap_days(bd, symbol, all_dates)

    # Process all dates
    sum_new_rows, fp_new_rows, empty_dates = process_gap_days(cd, symbol, tick_size, all_dates)

    # Record genuinely empty Binance dates so we never retry them
    if empty_dates:
        _save_ignored_gaps(symbol, empty_dates)
        print(f"  [{symbol}] Recorded {len(empty_dates)} known-empty Binance day(s) to ignored_gaps.txt")

    if not sum_new_rows:
        # Every single date was a Binance 404 — nothing to merge, but that's not a failure
        print(f"  [{symbol}] No new data recovered (all Binance 404/empty). Skipping merge.")
        return True

    # Load masters
    master_path = get_master_path(symbol)
    footprint_path = master_path.replace("Summary", "Footprint")
    existing_sum = pl.read_parquet(master_path) if os.path.exists(master_path) else None
    existing_fp = pl.read_parquet(footprint_path) if os.path.exists(footprint_path) else None

    # Helper to merge and sanitize
    def merge_and_sanitize(existing_pl, new_pd_list, time_col, is_fp):
        combined_pd = pd.concat(new_pd_list, ignore_index=True)
        for col in combined_pd.columns:
            series = combined_pd[col]
            if series.dtype == object:
                combined_pd[col] = series.where(series.apply(lambda x: not isinstance(x, float)), other=None)
        patch_pl = pl.from_pandas(combined_pd)
        if existing_pl is not None:
            combined = pl.concat([existing_pl, patch_pl], how="diagonal_relaxed")
        else:
            combined = patch_pl
        combined = combined.unique(subset=[time_col], keep="last")
        return rebuild_cvd_and_candles(combined, is_footprint=is_fp)

    # Merge Summary
    combined_sum = merge_and_sanitize(existing_sum, sum_new_rows, "TimeStamp", False)
    # Merge Footprint
    combined_fp = merge_and_sanitize(existing_fp, fp_new_rows, "Timestamp", True)

    # AUTO-ALIGN: Inner join on timestamps to ensure 100% parity
    sum_times = combined_sum.select(pl.col("TimeStamp").alias("_t")).unique()
    fp_times  = combined_fp.select(pl.col("Timestamp").alias("_t")).unique()
    common_times = sum_times.join(fp_times, on="_t", how="inner")

    combined_sum = (
        combined_sum
        .with_columns(pl.col("TimeStamp").alias("_t"))
        .join(common_times, on="_t", how="inner")
        .drop("_t")
    )
    combined_fp = (
        combined_fp
        .with_columns(pl.col("Timestamp").alias("_t"))
        .join(common_times, on="_t", how="inner")
        .drop("_t")
    )

    # Rebuild sequences to ensure they are mathematically perfect after the trim
    combined_sum = rebuild_cvd_and_candles(combined_sum, is_footprint=False)
    combined_fp = rebuild_cvd_and_candles(combined_fp, is_footprint=True)

    # Write masters
    ok_sum = safe_write(combined_sum, master_path)
    ok_fp = safe_write(combined_fp, footprint_path)

    if ok_sum and ok_fp:
        print(f"  [{symbol}] OK Master & Footprint patched: {len(combined_sum)} total rows ({len(sum_new_rows)} new days injected)")

    # Delete intermediate yearly parquets — master is the source of truth now
    if ok_sum and ok_fp:
        yearly_pattern_sum = master_path.replace(".parquet", "_????.parquet")
        yearly_pattern_fp = footprint_path.replace(".parquet", "_????.parquet")
        for yp in glob.glob(yearly_pattern_sum) + glob.glob(yearly_pattern_fp):
            try:
                os.remove(yp)
                print(f"  [{symbol}] Deleted yearly: {os.path.basename(yp)}")
            except Exception as e:
                print(f"  [{symbol}] WARN: Could not delete {os.path.basename(yp)}: {e}")

    # Cleanup raw downloads for this symbol to free disk space
    dl_dir = os.path.join(PIPELINE_DIR, "downloads", symbol)
    if os.path.exists(dl_dir):
        try:
            shutil.rmtree(dl_dir)
        except Exception as e:
            print(f"  [{symbol}] WARN: Could not clean downloads: {e}")

    gc.collect()
    return ok_sum and ok_fp

def main():
    parser = argparse.ArgumentParser(description="Fast Targeted Gap Patcher for 15m Parquet assets")
    parser.add_argument("--symbol", type=str, default=None, help="Single symbol to patch (e.g. AVAXUSDT). Default: all assets.")
    parser.add_argument("--dry-run", action="store_true", help="Only report gaps, do not download or patch.")
    args = parser.parse_args()

    targets = {}
    if args.symbol:
        sym = args.symbol.upper()
        if sym not in ASSETS:
            print(f"[ERR] {sym} not in asset registry. Valid: {list(ASSETS.keys())}")
            sys.exit(1)
        targets = {sym: ASSETS[sym]}
    else:
        targets = ASSETS

    mode = "DRY RUN" if args.dry_run else "PATCH MODE"
    print(f"\n{'='*60}")
    print(f"  PATCH_GAPS  -  {mode}  -  {len(targets)} asset(s)")
    print(f"  Threshold: day with <{MIN_CANDLES} candles is treated as incomplete")
    print(f"{'='*60}")

    failed = []
    start_all = datetime.now()

    for symbol, tick_size in targets.items():
        ok = patch_asset(symbol, tick_size, dry_run=args.dry_run)
        if not ok:
            failed.append(symbol)

    elapsed = datetime.now() - start_all
    print(f"\n{'='*60}")
    print(f"  COMPLETE  -  Elapsed: {elapsed}")
    if failed:
        print(f"  FAILED assets: {failed}")
        sys.exit(1)
    else:
        print(f"  All assets {'scanned' if args.dry_run else 'patched'} successfully.")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
