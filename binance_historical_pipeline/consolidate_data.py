import os
import sys
import numpy as np
import pandas as pd
import polars as pl
from datetime import datetime

# Globals set by patch_gaps.py
SYMBOL = "BTCUSDT"
TICK_SIZE = 15.0
INTERVAL = "15m"
DOWNLOADS = ""
BASE_SUMMARY_PARQUET = ""
BASE_FOOTPRINT_PARQUET = ""

IST_OFFSET = pl.duration(hours=5, minutes=30)

def _load_trades(path):
    if not os.path.exists(path): return None
    with open(path, "r") as f:
        first_line = f.readline()
    has_header = not first_line.split(",")[0].strip().isdigit()
    
    df = pl.scan_csv(path, has_header=has_header)
    
    if has_header:
        cols = df.columns
        df = df.rename({cols[0]: "agg_id", cols[1]: "price", cols[2]: "qty", cols[3]: "f_id", cols[4]: "l_id", cols[5]: "time", cols[6]: "buyer_maker"})
    else:
        df = df.rename({"column_1": "agg_id", "column_2": "price", "column_3": "qty", "column_4": "f_id", "column_5": "l_id", "column_6": "time", "column_7": "buyer_maker"})
        
    df = df.filter(pl.col("price").is_not_null() & pl.col("qty").is_not_null() & pl.col("time").is_not_null())
    df = df.with_columns([
        pl.col("price").cast(pl.Float64),
        pl.col("qty").cast(pl.Float64),
        pl.col("time").cast(pl.Int64),
        pl.col("buyer_maker").cast(pl.Boolean)
    ])
    
    df = df.with_columns([
        (pl.from_epoch(pl.col("time"), time_unit="ms") + IST_OFFSET).alias("time")
    ])
    df = df.filter(pl.col("time") > pl.datetime(2000, 1, 1))
    
    df = df.with_columns([
        pl.when(pl.col("buyer_maker")).then(pl.col("qty")).otherwise(0.0).alias("bid_qty"),
        pl.when(~pl.col("buyer_maker")).then(pl.col("qty")).otherwise(0.0).alias("ask_qty"),
        (pl.col("price") * pl.col("qty")).alias("usd_value"),
        ((pl.col("l_id") - pl.col("f_id") + 1).clip(lower_bound=1)).alias("trade_count")
    ])
    
    df = df.with_columns([
        pl.when(pl.col("buyer_maker")).then(pl.col("usd_value")).otherwise(0.0).alias("bid_usd"),
        pl.when(~pl.col("buyer_maker")).then(pl.col("usd_value")).otherwise(0.0).alias("ask_usd"),
        pl.when(pl.col("buyer_maker")).then(pl.col("trade_count")).otherwise(0).alias("bid_trades"),
        pl.when(~pl.col("buyer_maker")).then(pl.col("trade_count")).otherwise(0).alias("ask_trades"),
        ((pl.col("price") / TICK_SIZE).round() * TICK_SIZE).alias("Mid Price")
    ])
    
    return df.sort("time")

def _load_metrics(path):
    if not os.path.exists(path): return None
    df = pl.scan_csv(path)
    cols = df.columns
    time_col = "create_time" if "create_time" in cols else cols[0]
    
    df = df.with_columns([
        pl.col(time_col).cast(pl.String).str.to_datetime("%Y-%m-%d %H:%M:%S", strict=False).alias("time_dt")
    ])
    df = df.with_columns([
        pl.when(pl.col("time_dt").is_null())
        .then(pl.from_epoch(pl.col(time_col).cast(pl.Int64, strict=False), time_unit="ms"))
        .otherwise(pl.col("time_dt")).alias("time")
    ]).drop_nulls(subset=["time"])
    
    df = df.with_columns([(pl.col("time") + IST_OFFSET).alias("time")]).sort("time").unique(subset=["time"], keep="first")
    
    rename_map = {
        "sum_open_interest": "Agg. OI",
        "sum_toptrader_long_short_ratio": "Whale Ind",
        "count_long_short_ratio": "Long/Short Ratio (Account)"
    }
    df = df.rename({k: v for k, v in rename_map.items() if k in df.columns})
    
    keep = [c for c in ["Agg. OI", "Whale Ind", "Long/Short Ratio (Account)"] if c in df.columns]
    if not keep:
        return None
        
    return df.group_by_dynamic("time", every=INTERVAL).agg([pl.col(c).last().alias(c) for c in keep])

def _load_liquidations(path):
    if not os.path.exists(path): return None
    df = pl.scan_csv(path)
    if df.columns[0] != "time":
        df = df.rename({df.columns[0]: "time"})
    
    if "side" in df.columns and "qty" in df.columns:
        df = df.with_columns([
            (pl.from_epoch(pl.col("time").cast(pl.Int64), time_unit="ms") + IST_OFFSET).alias("time"),
            pl.when(pl.col("side") == "BUY").then(pl.col("qty").cast(pl.Float64)).otherwise(0.0).alias("Agg. Liq Short"),
            pl.when(pl.col("side") == "SELL").then(pl.col("qty").cast(pl.Float64)).otherwise(0.0).alias("Agg. Liq Long")
        ])
        return df.group_by_dynamic("time", every=INTERVAL).agg([
            pl.col("Agg. Liq Short").sum(),
            pl.col("Agg. Liq Long").sum()
        ])
    return None

def _load_funding(path):
    if not os.path.exists(path): return None
    df = pl.scan_csv(path)
    cols = df.columns
    time_col = "open_time" if "open_time" in cols else cols[0]
    funding_col = "funding_rate" if "funding_rate" in cols else (cols[7] if len(cols) > 7 else cols[-1])
    
    df = df.with_columns([
        (pl.from_epoch(pl.col(time_col).cast(pl.Int64), time_unit="ms") + IST_OFFSET).alias("time"),
        pl.col(funding_col).cast(pl.Float64).alias("Agg. Funding Rate")
    ])
    return df.group_by_dynamic("time", every=INTERVAL).agg([pl.col("Agg. Funding Rate").last()])

def process_day(date_str: str):
    """
    Process a single date.
    Reads aggTrades, metrics, liquidations, and funding.
    Returns (summary_df: pd.DataFrame, fp_df: pd.DataFrame).
    """
    try:
        t_dir = os.path.join(DOWNLOADS, SYMBOL, "aggTrades")
        t_path = os.path.join(t_dir, f"{SYMBOL}-aggTrades-{date_str}.csv")
        
        trades = _load_trades(t_path)
        if trades is None:
            return pd.DataFrame(), pd.DataFrame()
            
        # 1. Generate OHLCV + Basic Delta
        ohlcv = trades.group_by_dynamic("time", every=INTERVAL).agg([
            pl.col("price").first().alias("Open"),
            pl.col("price").max().alias("High"),
            pl.col("price").min().alias("Low"),
            pl.col("price").last().alias("Close"),
            pl.col("qty").sum().alias("Volume"),
            pl.col("bid_qty").sum().alias("Buy Qty"),
            pl.col("ask_qty").sum().alias("Sell Qty"),
        ])
        ohlcv = ohlcv.with_columns([
            (pl.col("Buy Qty") - pl.col("Sell Qty")).alias("Candle Delta")
        ])
        
        # 2. Build Footprint (grouped by time interval AND Mid Price)
        fp = trades.group_by_dynamic("time", every=INTERVAL, group_by="Mid Price").agg([
            pl.col("bid_qty").sum().alias("Bid Qty"),
            pl.col("ask_qty").sum().alias("Ask Qty"),
            pl.col("bid_usd").sum().alias("Bid USD"),
            pl.col("ask_usd").sum().alias("Ask USD"),
            pl.col("bid_trades").sum().alias("Bid Trades"),
            pl.col("ask_trades").sum().alias("Ask Trades"),
            (pl.col("bid_qty").sum() - pl.col("ask_qty").sum()).alias("Delta Qty"),
            (pl.col("bid_usd").sum() - pl.col("ask_usd").sum()).alias("Delta USD"),
            pl.col("qty").sum().alias("total_qty")
        ])
        
        # Calculate Price High and Low for each Mid Price band
        fp = fp.with_columns([
            (pl.col("Mid Price") - (TICK_SIZE / 2)).alias("Price Low"),
            (pl.col("Mid Price") + (TICK_SIZE / 2)).alias("Price High")
        ])
        
        # Determine POC per candle
        poc_df = fp.group_by("time").agg([
            pl.col("total_qty").max().alias("max_qty")
        ])
        
        fp = fp.join(poc_df, on="time", how="left")
        fp = fp.with_columns([
            pl.when(pl.col("total_qty") == pl.col("max_qty")).then(pl.lit("True")).otherwise(pl.lit("False")).alias("Is POC")
        ])
        
        # Calculate POC Price for summary
        poc_prices = fp.filter(pl.col("Is POC") == "True").group_by("time").agg([
            pl.col("Mid Price").first().alias("POC Price")
        ])
        
        # Merge POC Price into OHLCV
        ohlcv = ohlcv.join(poc_prices, on="time", how="left")
        
        # Add Timestamp strings
        ohlcv = ohlcv.with_columns([
            pl.col("time").dt.strftime("%Y-%m-%d %H:%M:%S").alias("TimeStamp"),
            pl.lit(SYMBOL).alias("Symbol")
        ])
        fp = fp.with_columns([
            pl.col("time").dt.strftime("%Y-%m-%d %H:%M:%S").alias("Timestamp"),
            pl.lit(SYMBOL).alias("Symbol"),
            pl.col("Mid Price").alias("POC Price") # for completeness
        ])
        
        # Drop max_qty from fp
        fp = fp.drop(["max_qty"])
        
        # Compute DataFrames
        ohlcv = ohlcv.collect()
        fp = fp.collect()
        
        if ohlcv.is_empty():
            return pd.DataFrame(), pd.DataFrame()
            
        # Convert to pandas for merging external data
        ohlcv_pd = ohlcv.to_pandas()
        
        # Metrics
        m_path = os.path.join(DOWNLOADS, SYMBOL, "metrics", f"{SYMBOL}-metrics-{date_str}.csv")
        metrics = _load_metrics(m_path)
        if metrics is not None:
            m_pd = metrics.collect().to_pandas()
            ohlcv_pd = pd.merge_asof(ohlcv_pd.sort_values("time"), m_pd.sort_values("time"), on="time", direction="backward")
            
        # Liquidations
        l_path = os.path.join(DOWNLOADS, SYMBOL, "liquidationSnapshot", f"{SYMBOL}-liquidationSnapshot-{date_str}.csv")
        liqs = _load_liquidations(l_path)
        if liqs is not None:
            l_pd = liqs.collect().to_pandas()
            ohlcv_pd = pd.merge_asof(ohlcv_pd.sort_values("time"), l_pd.sort_values("time"), on="time", direction="backward")
            
        # Funding
        f_path = os.path.join(DOWNLOADS, SYMBOL, "premiumIndexKlines", f"{SYMBOL}-5m-{date_str}.csv")
        if not os.path.exists(f_path):
            f_path = os.path.join(DOWNLOADS, SYMBOL, "premiumIndexKlines", f"{SYMBOL}-15m-{date_str}.csv")
        fund = _load_funding(f_path)
        if fund is not None:
            f_pd = fund.collect().to_pandas()
            ohlcv_pd = pd.merge_asof(ohlcv_pd.sort_values("time"), f_pd.sort_values("time"), on="time", direction="backward")
            
        # Final columns fill
        expected_cols = [
            'TimeStamp', 'Open', 'High', 'Low', 'Close', 'Volume', 'Buy Qty', 'Sell Qty', 
            'Candle Delta', 'POC Price', 'Agg. Liq Long', 'Agg. Liq Short', 'CVD', 
            'Long/Short Ratio (Account)', 'Whale Ind', 'Agg. OI', 'Agg. Funding Rate', 
            'RSI', 'Net Shorts', 'Net Longs', 'time', 'Symbol'
        ]
        
        for col in expected_cols:
            if col not in ohlcv_pd.columns:
                if col in ['Long/Short Ratio (Account)', 'Whale Ind']:
                    ohlcv_pd[col] = "0"
                else:
                    ohlcv_pd[col] = np.nan
                    
        # Filter down to expected columns in correct order (except Candle which is added by patch_gaps)
        final_summary = ohlcv_pd[expected_cols].copy()
        
        # Ensure Long/Short and Whale Ind are strings
        final_summary['Long/Short Ratio (Account)'] = final_summary['Long/Short Ratio (Account)'].astype(str)
        final_summary['Whale Ind'] = final_summary['Whale Ind'].astype(str)
        
        fp_pd = fp.to_pandas()
        
        return final_summary, fp_pd
        
    except Exception as e:
        print(f"Error processing {date_str}: {e}")
        return pd.DataFrame(), pd.DataFrame()

if __name__ == "__main__":
    pass
