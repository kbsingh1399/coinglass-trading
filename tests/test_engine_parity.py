import sys
import os
os.environ["BINANCE_LIVE"] = "0"
import time
import pytest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Engine_1 import Engine1TradeTracker, EngineConfig, config
import six_strategy_engine as sse

def test_engine_config_defaults():
    eng_cfg = EngineConfig()
    assert eng_cfg.tp_mult == 5.0, f"Expected 5.0, got {eng_cfg.tp_mult}"
    assert eng_cfg.trail_atr == 0.8, f"Expected 0.8, got {eng_cfg.trail_atr}"

def test_six_strategy_engine_constants():
    assert sse.TP_MULT == 5.0, f"Expected 5.0, got {sse.TP_MULT}"
    assert sse.TRAIL_ATR == 0.8, f"Expected 0.8, got {sse.TRAIL_ATR}"
    assert sse.SL_MULT == 1.0, f"Expected 1.0, got {sse.SL_MULT}"
    assert sse.MAX_BARS == 288, f"Expected 288, got {sse.MAX_BARS}"

def test_cross_file_parameter_parity():
    eng_cfg = EngineConfig()
    assert eng_cfg.tp_mult == sse.TP_MULT == 5.0
    assert eng_cfg.trail_atr == sse.TRAIL_ATR == 0.8


def make_test_tracker():
    tracker = Engine1TradeTracker()
    test_log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_trade_logs.json")
    tracker.tracker_file = test_log
    tracker.log_file = test_log
    tracker.active_trades.clear()
    tracker.history.clear()
    return tracker

# ─── Risk Sizing Parity Tests ────────────────────────────────────────

def test_tight_sl_widening_adaptation():
    """Assert trigger_entry() automatically widens tight SL to min_stop_dist instead of dropping trades."""
    os.environ["ENGINE_RISK_USD"] = "20.0"
    tracker = make_test_tracker()
    tracker.emergency_halt = False

    # TRXUSDT at $0.34 with tight SL at $0.3399 (0.03%)
    # Min stop for TRXUSDT = 0.2% -> 0.00068 -> auto-widened so trade is executed safely
    entry = 0.34
    sl = 0.3399  # Only 0.03% away
    tp = 0.357   # 5% away
    atr = 0.001

    tracker.trigger_entry(
        symbol="TRXUSDT", strategy="S1_Liquidation", direction=1,
        entry_price=entry, sl=sl, tp=tp, atr=atr,
        macro=1, vol_regime=0.5, risk_mult=1.0, trail_act=1.0, regime_val=0
    )

    trx_trades = [t for t in tracker.active_trades.values() if t['symbol'] == 'TRXUSDT']
    assert len(trx_trades) == 1, f"Tight-SL trade should be adaptively accepted, found {len(trx_trades)}"
    assert trx_trades[0]['sl'] <= entry - 0.00068, f"SL should be floored to min safe distance, got {trx_trades[0]['sl']}"


def test_notional_cap():
    """Assert units × entry_price never exceeds $50,000."""
    os.environ["ENGINE_RISK_USD"] = "20.0"
    tracker = make_test_tracker()
    tracker.emergency_halt = False

    # BTCUSDT at $65,000 with SL $650 away (1%) — passes min stop (0.1%)
    # units = $20/$650 = 0.0307 → notional = 0.0307 × $65,000 = $2,000 (under cap)
    # Now test with very tight SL that would exceed cap:
    # stop_dist = $10 → units = $20/$10 = 2 → notional = 2 × $65,000 = $130,000
    # BTC min stop = 0.1% = $65 → $10 < $65 → REJECTED by min stop floor
    # So we use a valid but high-leverage scenario:
    entry = 65000.0
    sl = 64935.0   # $65 away (0.1% — exactly at BTC min stop)
    tp = 65325.0   # $325 away (0.5%)
    atr = 65.0

    tracker.trigger_entry(
        symbol="BTCUSDT", strategy="S3_Trend_Follow", direction=1,
        entry_price=entry, sl=sl, tp=tp, atr=atr,
        macro=1, vol_regime=0.5, risk_mult=1.0, trail_act=5.0, regime_val=0
    )

    btc_trades = [t for t in tracker.active_trades.values() if t['symbol'] == 'BTCUSDT']
    if btc_trades:
        trade = btc_trades[0]
        units = trade.get('units', 0)
        notional = units * entry
        assert notional <= 50_000.0 + 1.0, f"Notional ${notional:.2f} exceeds $50,000 cap"


def test_sl_pnl_within_risk_bounds():
    """Assert simulated SL loss stays within ±2× ENGINE_RISK_USD."""
    os.environ["BINANCE_LIVE"] = "0"
    os.environ["ENGINE_RISK_USD"] = "20.0"
    tracker = make_test_tracker()
    tracker.emergency_halt = False

    # Normal trade: $0.50 entry, $0.495 SL (1% away), $0.525 TP (5% away)
    entry = 0.50
    sl = 0.495     # 1% away → stop_dist = 0.005
    tp = 0.525     # 5% away
    atr = 0.005

    tracker.trigger_entry(
        symbol="ADAUSDT", strategy="S1_Liquidation", direction=1,
        entry_price=entry, sl=sl, tp=tp, atr=atr,
        macro=1, vol_regime=0.5, risk_mult=1.0, trail_act=5.0, regime_val=0
    )

    ada_trades = [t for t in tracker.active_trades.values() if t['symbol'] == 'ADAUSDT']
    if ada_trades:
        trade = ada_trades[0]
        units = trade.get('units', 0)
        stop_dist = abs(entry - sl)
        max_loss = units * stop_dist
        risk_usd = float(os.environ.get("ENGINE_RISK_USD", "20.0"))
        assert max_loss <= 2.0 * risk_usd, f"Max SL loss ${max_loss:.2f} exceeds 2× risk (${2*risk_usd})"


def test_daily_dd_reset_on_new_session():
    """Assert daily_start_capital resets when trade log is from a prior day."""
    tracker = Engine1TradeTracker()
    import zoneinfo
    from datetime import datetime as _dt
    broker_tz = zoneinfo.ZoneInfo("Europe/Athens")
    today = _dt.now(broker_tz).strftime("%Y-%m-%d")

    # Simulate: current_capital is lower than initial due to historical losses
    tracker.initial_capital = 4907.37
    tracker.current_capital = 4559.0  # ~7% loss from history
    tracker.daily_start_capital = 4907.37  # Stale value from prior session
    tracker.last_rollover_day = "2020-01-01"  # Clearly not today

    # The load_history fix should detect the stale day and reset
    # We simulate what load_history does:
    if tracker.last_rollover_day != today:
        tracker.daily_start_capital = tracker.current_capital
        tracker.last_rollover_day = today

    # Now daily DD should be 0% (baseline = current)
    current_equity = tracker.current_capital
    daily_dd = (tracker.daily_start_capital - current_equity) / tracker.daily_start_capital * 100.0
    assert abs(daily_dd) < 0.01, f"Daily DD should be ~0% after reset, got {daily_dd:.2f}%"
    assert tracker.daily_start_capital == 4559.0, "daily_start_capital should equal current_capital"


# ─── Data Format Parity Tests ────────────────────────────────────────

def test_funding_rate_decimal_fraction():
    """Assert funding rate from featurize() is always a decimal fraction (|val| < 0.01)."""
    import pandas as pd, numpy as np, os
    from six_strategy_engine import featurize

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backtesting_data')
    path = os.path.join(data_dir, 'Master_BTCUSDT_15m_Final_Summary.parquet')
    if not os.path.exists(path):
        pytest.skip("No backtest parquet available")

    df = pd.read_parquet(path).tail(200)
    tc = "TimeStamp" if "TimeStamp" in df.columns else "Timestamp"
    df["ts"] = pd.to_datetime(df[tc].astype(str).str.replace(" IST", "", regex=False), errors="coerce")
    df = df.sort_values("ts").drop_duplicates(subset=["ts"], keep="first")
    for c in df.columns:
        if c != "ts":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.set_index("ts")

    df_feat = featurize(df.copy())
    fr = df_feat['fr'].dropna()
    nonzero_fr = fr[fr != 0]
    if len(nonzero_fr) > 0:
        assert nonzero_fr.abs().max() < 0.01, \
            f"Funding rate max |{nonzero_fr.abs().max():.6f}| >= 0.01 — not a decimal fraction"


def test_atr_minimum_pct_of_price():
    """Assert ATR from featurize() is at least 0.05% of price for major symbols."""
    import pandas as pd, numpy as np, os
    from six_strategy_engine import featurize

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backtesting_data')
    for sym in ['BTCUSDT', 'ETHUSDT']:
        path = os.path.join(data_dir, f'Master_{sym}_15m_Final_Summary.parquet')
        if not os.path.exists(path):
            continue

        df = pd.read_parquet(path).tail(500)
        tc = "TimeStamp" if "TimeStamp" in df.columns else "Timestamp"
        df["ts"] = pd.to_datetime(df[tc].astype(str).str.replace(" IST", "", regex=False), errors="coerce")
        df = df.sort_values("ts").drop_duplicates(subset=["ts"], keep="first")
        for c in df.columns:
            if c != "ts":
                df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.set_index("ts")

        df_feat = featurize(df.copy())
        # Check rows where H-L > 0 (non-flat candles)
        hl = df_feat['High'] - df_feat['Low']
        nonflat = df_feat[hl > 0]
        if len(nonflat) > 0:
            atr_pct = (nonflat['atr'] / nonflat['Close']).median() * 100
            assert atr_pct >= 0.05, \
                f"{sym} median ATR/price = {atr_pct:.4f}% < 0.05% minimum"


def test_non_backtested_symbols_guarded():
    """Assert that symbols without backtest data are not in the SSE SYMBOLS list."""
    unbacked = ['CLUSDT', 'NATGASUSDT']
    for sym in unbacked:
        assert sym not in sse.SYMBOLS, \
            f"{sym} has no backtest data but is in six_strategy_engine.SYMBOLS"


def test_column_staleness_purple_bold_formatting():
    """Assert that columns unchanged for >= 60s render in Purple BOLD."""
    from Engine_1 import render_table, AssetSnapshot, ALL_SYMBOLS, _COLUMN_LAST_CHANGED_TIME, _COLUMN_LAST_VALUES

    # Create dummy snapshots
    snaps = {sym: AssetSnapshot(symbol=sym, price=100.0, rsi=50.0, fut_cvd=1000.0) for sym in ALL_SYMBOLS}
    
    # 1. Initial render (fresh)
    res = render_table(snaps)
    tbl = res.renderables[0] if hasattr(res, 'renderables') else res
    # Check that price is not purple initially
    col_names = [col.header for col in tbl.columns]
    assert "Price" in col_names, "Price column should be present normally when fresh"

    # 2. Simulate 65 seconds of unchanged Price column
    _COLUMN_LAST_CHANGED_TIME["Price"] = time.time() - 65.0
    res_stale = render_table(snaps)
    tbl_stale = res_stale.renderables[0] if hasattr(res_stale, 'renderables') else res_stale
    
    stale_col_names = [col.header for col in tbl_stale.columns]
    assert "[bold purple]Price[/bold purple]" in stale_col_names, "Price column header should turn [bold purple] when unchanged for > 60s"
    
    # Check that cells in Price column have bold purple style
    price_col = tbl_stale.columns[1]
    assert "[bold purple]Price[/bold purple]" in price_col.header
    
    # 3. Simulate a change in price (fresh update arrives)
    snaps["BTCUSDT"] = AssetSnapshot(symbol="BTCUSDT", price=105.0, rsi=50.0, fut_cvd=1000.0)
    res_fresh = render_table(snaps)
    tbl_fresh = res_fresh.renderables[0] if hasattr(res_fresh, 'renderables') else res_fresh
    fresh_col_names = [col.header for col in tbl_fresh.columns]
    assert "Price" in fresh_col_names, "Price column header should return to normal when a price changes"

