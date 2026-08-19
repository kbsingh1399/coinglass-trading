import os
import sys
import glob
from datetime import datetime, timedelta
import polars as pl

PARQUET_DIR = r"G:\My Drive\_Trading_Data\15m\parquet"
IGNORED_GAPS_FILE = r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\binance_historical_pipeline\ignored_gaps.txt"

def _load_ignored_gaps(symbol: str) -> set[str]:
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

def get_expected_candles(interval="15m"):
    if interval == "15m":
        return 96
    return 96

def check_authenticity():
    print("=" * 60)
    print("  AUTHENTICITY CHECK")
    print("=" * 60)
    
    summary_files = glob.glob(os.path.join(PARQUET_DIR, "Master_*_15m_Final_Summary.parquet"))
    footprint_files = glob.glob(os.path.join(PARQUET_DIR, "Master_*_15m_Final_Footprint.parquet"))
    
    if not summary_files:
        print("[ERR] No Master Summary parquet files found.")
        return False
        
    all_good = True
    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_dt = datetime.now() - timedelta(days=1)
    
    for f in summary_files + footprint_files:
        is_footprint = "Footprint" in f
        t_col = "Timestamp" if is_footprint else "TimeStamp"
        symbol = os.path.basename(f).split("_")[1]
        
        ignored = _load_ignored_gaps(symbol)
        
        try:
            s = pl.read_parquet(f, columns=[t_col])[t_col]
        except Exception as e:
            print(f"[ERR] Failed to read {os.path.basename(f)}: {e}")
            all_good = False
            continue
            
        date_col = s.str.slice(0, 10)
        counts = pl.DataFrame({"date": date_col}).group_by("date").len()
        counts_dict = dict(zip(counts["date"].to_list(), counts["len"].to_list()))
        
        min_date = date_col.min()
        if not min_date:
            print(f"[ERR] {os.path.basename(f)} is empty.")
            all_good = False
            continue
            
        start_dt = datetime.strptime(min_date, "%Y-%m-%d")
        cur = start_dt
        expected = get_expected_candles()
        
        file_good = True
        missing_dates = []
        incomplete_dates = []
        
        while cur <= yesterday_dt:
            d_str = cur.strftime("%Y-%m-%d")
            # Skip launch day because it rarely has 96 candles
            if d_str == min_date or d_str in ignored:
                cur += timedelta(days=1)
                continue
                
            count = counts_dict.get(d_str, 0)
            if count == 0:
                missing_dates.append(d_str)
            elif count < 92:
                incomplete_dates.append((d_str, count))
                
            cur += timedelta(days=1)
            
        if missing_dates:
            print(f"[ERR] {symbol} {'Footprint' if is_footprint else 'Summary'} is missing {len(missing_dates)} days (e.g. {missing_dates[:3]}).")
            file_good = False
            
        if incomplete_dates:
            print(f"[ERR] {symbol} {'Footprint' if is_footprint else 'Summary'} has {len(incomplete_dates)} incomplete days < 92 candles (e.g. {incomplete_dates[:3]}).")
            file_good = False
                
        if file_good:
            print(f"  [OK] {symbol} {'Footprint' if is_footprint else 'Summary'} is mathematically complete from {min_date} to {yesterday_dt.strftime('%Y-%m-%d')}.")
        else:
            all_good = False
            
    if all_good:
        print("\n[SUCCESS] All files are 100% authenticated.")
        return True
    else:
        print("\n[FAILURE] Authenticity check failed due to missing or incomplete data.")
        return False

if __name__ == "__main__":
    if check_authenticity():
        sys.exit(0)
    else:
        sys.exit(1)
