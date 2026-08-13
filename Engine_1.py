# C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1\Engine_1.py
# Production-Grade Coinglass + Binance Footprint Scraper Terminal
# Built from scratch - fully modular, clean, and robust.

from __future__ import annotations
import os
import sys
import os

# Enable instant unbuffered stdout/stderr flushing for real-time live terminal logs
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

import time
import json
import asyncio
import signal
import collections
import dataclasses
import threading
import math
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

import aiohttp
import websockets
import socket
from playwright.async_api import async_playwright, Page, BrowserContext

base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(base_dir, "engine_components"))
load_dotenv(os.path.join(base_dir, ".env"))
load_dotenv(os.path.join(base_dir, "..", ".env"))

# Six Strategy Engine (ports run_all_6.py verified strategies)
from six_strategy_engine import LiveSixStrategyPredictor, STRATEGY_NAMES as SIX_STRAT_NAMES
from rich.console import Console
from rich.live import Live
from rich.table import Table
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import pandas as pd
import numpy as np

# Reconfigure sys.stdout and sys.stderr to use UTF-8 encoding to prevent UnicodeEncodeError on Windows
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

import ctypes

def get_process_memory_usage() -> int:
    try:
        class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
                ("PrivateUsage", ctypes.c_size_t),
            ]
        psapi = ctypes.windll.psapi
        kernel32 = ctypes.windll.kernel32
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        
        pmc = PROCESS_MEMORY_COUNTERS_EX()
        pmc.cb = ctypes.sizeof(pmc)
        handle = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.cb):
            return pmc.PrivateUsage
    except Exception:
        pass
    return 0

base_dir = os.path.dirname(os.path.abspath(__file__))
EXECUTION_MODE = os.environ.get("EXECUTION_MODE", "LIVE")
ENGINE_RISK_PCT = float(os.environ.get("ENGINE_RISK_PCT", "0.005"))
ENGINE_RISK_USD = float(os.environ.get("ENGINE_RISK_USD", "0.0"))
MT5_LIVE = os.environ.get("MT5_LIVE", "0") == "1"

# Strategy identity constants (used by Engine1TradeTracker cooldown logic)
ACTIVE_STRATEGY = os.environ.get("ACTIVE_STRATEGY", "ml_alpha_squeezer")
STRATEGY_DISPLAY_NAME = ACTIVE_STRATEGY.replace("_", " ").title().replace(" ", "_")


def _parse_suffix_float(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip().replace(",", "")
    # Replace all unicode minus variants with ASCII minus
    for ch in ("\u2212", "\u2012", "\u2013", "\u2014"):
        s = s.replace(ch, "-")
    if not s or s.lower() == "n/a" or s == "--" or s.lower() == "nan" or s == "∅":
        return None
    try:
        mul = 1.0
        if s.endswith("%"):
            s = s[:-1]
        if s.lower().endswith("k"):
            mul = 1000.0
            s = s[:-1]
        elif s.lower().endswith("m"):
            mul = 1000000.0
            s = s[:-1]
        elif s.lower().endswith("b"):
            mul = 1000000000.0
            s = s[:-1]
        elif s.lower().endswith("t"):
            mul = 1000000000000.0
            s = s[:-1]
        f = float(s)
        return f * mul if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None

def parse_float(val: Any) -> float:
    res = _parse_suffix_float(val)
    return res if res is not None else 0.0

def finite_float_or_none(val: Any) -> float | None:
    return _parse_suffix_float(val)

def get_historical_timestamps(symbol: str, start_time_ts: int, steps: int) -> List[int]:
    is_crypto = symbol not in ["XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"]
    if is_crypto:
        return [int(start_time_ts - i * 900) for i in range(steps)]

    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    ny_tz = ZoneInfo("America/New_York")

    def is_active(dt):
        day = dt.weekday()
        hour = dt.hour
        if day == 4:  # Friday
            if hour >= 17: return False
        elif day == 5:  # Saturday
            return False
        elif day == 6:  # Sunday
            if hour < 18: return False
        if day in (0, 1, 2, 3):  # Mon-Thu
            if hour == 17: return False
        return True

    dt = datetime.fromtimestamp(start_time_ts, tz=ny_tz)
    dt = dt.replace(minute=(dt.minute // 15) * 15, second=0, microsecond=0)

    while not is_active(dt):
        dt -= timedelta(minutes=15)

    timestamps = []
    for _ in range(steps):
        timestamps.append(int(dt.timestamp()))
        dt -= timedelta(minutes=15)
        while not is_active(dt):
            dt -= timedelta(minutes=15)

    return timestamps

def calculate_commodity_gap(symbol: str, latest_time: int, current_time: int) -> int:
    is_crypto = symbol not in ["XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"]
    if is_crypto:
        return max(0, int((current_time - latest_time) / 900))
    timestamps = get_historical_timestamps(symbol, current_time, 2000)
    for idx, ts in enumerate(timestamps):
        if ts <= latest_time:
            return idx
    return 1000

# --- GLOBAL CONFIGURATION ---
URL = "https://www.coinglass.com/tv/layout/s9"
TAB1_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT"]
TAB2_SYMBOLS = ["AVAXUSDT", "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT", "XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"]
ALL_SYMBOLS = TAB1_SYMBOLS + TAB2_SYMBOLS
REFRESH_HZ = 2.0  # 2 Hz rendering = 0.5s interval
STALE_NS = 5_000_000_000  # 5 seconds staleness threshold

# --- INDICATOR CONFIGURATION ---
_INDICATORS_TO_INJECT = [
    # (search_term, check_str, modal_type)
    ("Aggregated Futures Cumulative Volume Delta (CVD)", "futures cumulative", "coinglass"),
    ("Aggregated Spot Cumulative Volume Delta (CVD)",    "spot cumulative",    "coinglass"),
    ("Relative Strength Index",                          "rsi",                "tv"),
    ("Funding Rates",                                    "funding rate",       "coinglass"),
    ("Aggregated Liquidations",                          "liquidations",       "coinglass"),
    ("Long/Short Ratio (Accounts)",                      "long/short",         "coinglass"),
    ("Aggregated Open Interest(STABLECOIN-margined,Candles)", "open interest",  "coinglass"),
    ("Aggregated Futures Bid & Ask",                     "bid & ask",          "coinglass"),
    ("Whale Index",                                      "whale index",        "coinglass"),
    ("Taker Buy/Sell Count",                             "taker buy/sell",     "coinglass"),
]

# --- STATE MANAGEMENT ---
_FLOAT_FIELDS = {
    'price', 'volume', 'rsi', 'fut_cvd', 'spot_cvd', 'liq_long', 'liq_short',
    'funding', 'ls_ratio', 'oi', 'fp_delta', 'fp_poc', 'coins_bid', 'coins_ask',
    'dollars_bid', 'dollars_ask', 'whale_idx', 'tk_buy_cnt', 'tk_sell_cnt'
}

@dataclasses.dataclass
class EngineConfig:
    tp_mult: float = 5.0
    trail_atr: float = 0.8
    risk_per_trade: float = 10.0
    max_daily_risk: float = 150.0
    max_drawdown_pct: float = 8.0
    fee_pct: float = 0.0008

config = EngineConfig()

@dataclasses.dataclass
class AssetSnapshot:
    symbol: str
    price: float = 0.0
    volume: float = 0.0
    rsi: float = 0.0
    fut_cvd: float = 0.0
    spot_cvd: float = 0.0
    liq_long: float = 0.0
    liq_short: float = 0.0
    funding: float = 0.0
    ls_ratio: float = 0.0
    oi: float = 0.0
    fp_delta: float = 0.0
    fp_poc: float = 0.0
    coins_bid: float = 0.0
    coins_ask: float = 0.0
    dollars_bid: float = 0.0
    dollars_ask: float = 0.0
    whale_idx: float = 0.0
    tk_buy_cnt: float = 0.0
    tk_sell_cnt: float = 0.0
    strategy_armed: str = ""
    ts_ns: int = 0
    seq: int = 0

    def __post_init__(self):
        for f in _FLOAT_FIELDS:
            try:
                setattr(self, f, float(getattr(self, f)))
            except (ValueError, TypeError):
                setattr(self, f, 0.0)

class BinanceBrokerAdapter:
    def __init__(self, binance_broker, tracker):
        self.broker = binance_broker
        self.tracker = tracker
        self.dry_run = binance_broker.dry_run

    @property
    def account_size(self):
        return self.tracker.current_capital

    @account_size.setter
    def account_size(self, val):
        pass

    def connect(self) -> bool:
        return self.broker.connect()

    def execute_trade(self, symbol, direction, entry_price, sl, tp, strategy):
        # Determine risk capital
        import os
        env_risk_usd = float(os.environ.get("ENGINE_RISK_USD", "0.0"))
        if env_risk_usd > 0.0:
            risk_capital = env_risk_usd
        else:
            risk_capital = self.tracker.current_capital * ENGINE_RISK_PCT

        res = self.broker.execute_trade(
            binance_symbol=symbol,
            direction=direction,
            bin_entry=entry_price,
            bin_sl=sl,
            bin_tp=tp,
            strategy=strategy,
            risk_capital=risk_capital
        )
        if res:
            return {
                "mt5_symbol": res["symbol"],
                "mt5_ticket": res["order_id"],
                "mt5_order": res["order_id"],
                "mt5_deal": res["order_id"],
                "mt5_entry": res["entry_price"],
                "mt5_sl": res["sl_price"],
                "mt5_tp": res["tp_price"],
                "lot": res["lot"],
                "is_pending": res.get("is_pending", False)
            }
        else:
            print(f"[Broker] [WARNING] Order execution returned None for {symbol} ({strategy}). Possible margin/API restriction.")
        return None

    def close_position(self, symbol, reason="ENGINE_EXIT") -> bool:
        return self.broker.close_position(symbol, reason)

    def modify_sltp(self, symbol, ticket, sl, tp) -> bool:
        return self.broker.modify_sltp(symbol, ticket, sl, tp)

    def is_order_pending(self, order_ticket) -> bool:
        return False

    def has_position(self, ticket) -> bool:
        if self.dry_run:
            return True
        symbol = None
        for t in self.tracker.active_trades.values():
            if t.get("mt5_ticket") == ticket or t.get("mt5_order") == ticket:
                symbol = t.get("symbol")
                break
        if not symbol or not self.broker.is_valid_symbol(symbol):
            return False

        try:
            res = self.broker._request("GET", "/fapi/v2/positionRisk", params={"symbol": symbol}, signed=True, max_retries=1)
            if res:
                for p in res:
                    if p["symbol"] == symbol:
                        return float(p.get("positionAmt", 0.0)) != 0.0
        except Exception:
            pass
        return False

    def list_engine_positions(self) -> list:
        if self.dry_run:
            return []
        try:
            res = self.broker._request("GET", "/fapi/v2/positionRisk", signed=True, max_retries=1)
            if res:
                class PositionObj:
                    def __init__(self, ticket):
                        self.ticket = ticket
                active_positions = []
                for p in res:
                    if float(p.get("positionAmt", 0.0)) != 0.0:
                        # Find corresponding order ID ticket from active trades
                        ticket = None
                        for t in self.tracker.active_trades.values():
                            if t.get("symbol") == p.get("symbol"):
                                ticket = t.get("mt5_ticket")
                                break
                        if ticket is not None:
                            active_positions.append(PositionObj(ticket))
                return active_positions
        except Exception as e:
            print(f"[Binance] Error querying live positionRisk: {e}")
        return []


class LiveTradeTracker:
    REENTRY_COOLDOWN_TP_SECS = 3600   # 1 hour
    REENTRY_COOLDOWN_SL_SECS = 1800   # 30 minutes

    def _cooldown_key(self, strategy: str, symbol: str) -> str:
        return f"{strategy}:{symbol}"

    def _cooldown_secs_after_close(self, strategy: str, reason: str) -> int:
        six_strat_names = {
            "S1_Liquidation", "S2_CVD_Momentum", "S3_Trend_Follow",
            "S4_Mean_Reversion", "S5_Vol_Breakout", "S6_OI_Coherence"
        }
        if strategy in six_strat_names:
            if reason == "TP": return self.REENTRY_COOLDOWN_TP_SECS
            return self.REENTRY_COOLDOWN_SL_SECS
        if strategy == "ML_Liquidation_Runner":
            if reason == "TP": return 0
            if reason in ("SL", "BE", "TRAIL"): return 15 * 60
        if strategy in (STRATEGY_DISPLAY_NAME, "AlphaSqueezer_V17", "AlphaSqueezer_V11"):
            if reason == "TP": return self.REENTRY_COOLDOWN_TP_SECS
            return self.REENTRY_COOLDOWN_SL_SECS
        if strategy == "ML_Trend_Pull":
            if reason == "TP": return self.REENTRY_COOLDOWN_TP_SECS
            return self.REENTRY_COOLDOWN_SL_SECS
        return 15 * 60

    def __init__(self, initial_capital: float = 10000.0, base_dir: str = "."):
        self.base_dir = base_dir
        self.tracker_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "Engine_1_trade_logs.json"
        )
        self.log_file = self.tracker_file
        self.lock = threading.RLock()
        
        # --- Binance Broker Initialization ---
        from concurrent.futures import ThreadPoolExecutor
        self.broker_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="BinanceBroker")

        from engine_components.binance_broker import BinanceBroker
        binance_live = os.environ.get("BINANCE_LIVE", "1") != "0"
        use_testnet = os.environ.get("BINANCE_USE_TESTNET", "true").lower() == "true"
        
        raw_binance_broker = BinanceBroker(
            dry_run=not binance_live,
            account_size=initial_capital,
            risk_pct=ENGINE_RISK_PCT,
            use_testnet=use_testnet
        )
        self.mt5_broker = BinanceBrokerAdapter(raw_binance_broker, self)
        
        if self.mt5_broker.connect():
            details = raw_binance_broker.get_account_details()
            if details and details.get("balance", 0.0) > 0.0:
                initial_capital = details["balance"]
        # -------------------------------------
        
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.daily_start_capital = initial_capital
        self.emergency_halt = False
        self.on_close_callbacks = []
        
        import zoneinfo
        from datetime import datetime
        broker_tz = zoneinfo.ZoneInfo("Europe/Athens")
        self.last_rollover_day = datetime.now(broker_tz).strftime("%Y-%m-%d")
        self.active_trades: Dict[str, dict] = {}
        self.closed_trades: List[dict] = []
        self.last_entry_bar: Dict[str, str] = {}
        self.reentry_cooldown_until: Dict[str, float] = {}
        
        self._load_state = self.load_history
        self.load_history()

    def _broker_submit(self, fn, *args, **kwargs) -> None:
        if not hasattr(self, "broker_executor") or self.broker_executor is None:
            print(f"[Binance][FATAL] broker_executor missing — cannot dispatch {fn.__name__}")
            return
        try:
            fut = self.broker_executor.submit(fn, *args, **kwargs)
            def _log_done(f):
                exc = f.exception()
                if exc:
                    print(f"[Binance] Async broker call {fn.__name__} failed: {exc}")
            fut.add_done_callback(_log_done)
        except Exception as exc:
            print(f"[Binance] Failed to submit broker action: {exc}")

    def load_history(self):
        """Load only from this engine's own log — never from Engine 3 whose
        pnl_usd uses an incompatible unit-based sizing model."""
        with self.lock:
            if not os.path.exists(self.log_file):
                return
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Support envelope format with __meta__
                meta = {}
                if isinstance(data, dict) and '__meta__' in data:
                    meta = data['__meta__']
                    data = data.get('trades', [])
                if not isinstance(data, list):
                    return
                self.last_entry_bar = meta.get('last_entry_bar', {})
                # FIX 2: Strip test/dry-run artifacts injected by boot scripts.
                # These have synthetic trade_ids and corrupt the P&L baseline.
                raw_history = [t for t in data if t.get('exit_price')]
                self.history = [
                    t for t in raw_history
                    if 'test' not in t.get('trade_id', '').lower()
                    and 'emergency_test' not in t.get('trade_id', '').lower()
                ]
                self.current_capital = self.initial_capital
                self.daily_start_capital = meta.get('daily_start_capital', self.current_capital)
                self.last_rollover_day = meta.get('last_rollover_day', self.last_rollover_day)

                # FIX: If the log is from a prior session (different day), reset daily DD baseline
                # to prevent stale cumulative losses from triggering an immediate emergency halt.
                import zoneinfo
                from datetime import datetime as _dt
                broker_tz = zoneinfo.ZoneInfo("Europe/Athens")
                today = _dt.now(broker_tz).strftime("%Y-%m-%d")
                if self.last_rollover_day != today:
                    self.daily_start_capital = self.current_capital
                    self.last_rollover_day = today
                    print(f"[RiskGovernor] New session detected (last rollover: {meta.get('last_rollover_day', 'unknown')}). "
                          f"Daily DD baseline reset to ${self.current_capital:.2f}")
                for t in data:
                    if not t.get('exit_price') and t.get('trade_id'):
                        self.active_trades[t['trade_id']] = t
            except Exception as e:
                print(f"[TradeTracker] [ERROR] Failed to load trade history: {e}")

    def save_history(self):
        with self.lock:
            try:
                if len(self.history) > 5000:
                    self.history = self.history[-5000:]
                all_trades = list(self.history) + list(self.active_trades.values())
                envelope = {
                    '__meta__': {
                        'last_entry_bar': dict(self.last_entry_bar),
                        'daily_start_capital': self.daily_start_capital,
                        'last_rollover_day': self.last_rollover_day
                    },
                    'trades': all_trades
                }
                tmp = self.log_file + ".tmp"
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(envelope, f, indent=4)
                os.replace(tmp, self.log_file)
            except Exception:
                pass

    def update_day(self) -> None:
        with self.lock:
            import zoneinfo
            from datetime import datetime
            broker_tz = zoneinfo.ZoneInfo("Europe/Athens")
            now_day = datetime.now(broker_tz).strftime("%Y-%m-%d")
            
            if self.last_rollover_day != now_day:
                active_list = list(self.active_trades.values())
                unrealized_pnl = sum(t.get('live_pnl_usd', 0.0) for t in active_list)
                current_equity = self.current_capital + unrealized_pnl
                
                self.daily_start_capital = current_equity
                self.last_rollover_day = now_day
                print(f"[RiskGovernor] Daily starting capital rolled over to ${self.daily_start_capital:.2f} at Athens server day {now_day}")

    def trigger_entry(self, symbol: str, strategy: str, direction: int, entry_price: float, sl: float, tp: float, atr: float, macro: int, vol_regime: float, risk_mult: float = 1.0, trail_act: float = 0.5, regime_val: int = 0) -> None:
        with self.lock:
            if getattr(self, 'emergency_halt', False):
                print(f"[RiskGovernor] Entry blocked. Symbol={symbol} Strategy={strategy}. Emergency halt active.")
                return

            # --- GLOBAL RISK GOVERNOR (Blueberry Funded Account Limits) ---
            active_list = list(self.active_trades.values())
            unrealized_pnl = sum(t.get('live_pnl_usd', 0.0) for t in active_list)
            current_equity = self.current_capital + unrealized_pnl

            # 1. Daily Drawdown Check (Hard limit 5%, Guardrail 4.0%)
            daily_dd = (self.daily_start_capital - current_equity) / self.daily_start_capital * 100.0 if self.daily_start_capital > 0 else 0.0
            if daily_dd >= 4.0:
                print(f"[RiskGovernor] Entry blocked. Symbol={symbol} Strategy={strategy}. Daily drawdown ({daily_dd:.2f}%) exceeds 4% guardrail.")
                return

            # 2. Total Drawdown Check (Hard limit 10%, Guardrail 8.0% of $5,000 initial capital)
            total_dd = (self.initial_capital - current_equity) / self.initial_capital * 100.0
            if total_dd >= 8.0:
                print(f"[RiskGovernor] Entry blocked. Symbol={symbol} Strategy={strategy}. Total drawdown ({total_dd:.2f}%) exceeds 8% guardrail.")
                return

            cool_key = self._cooldown_key(strategy, symbol)
            cooldown_until = self.reentry_cooldown_until.get(cool_key, 0.0)
            if time.time() < cooldown_until:
                print(f"[RiskGovernor] Entry blocked by cooldown. Symbol={symbol} Strategy={strategy} Remaining={(cooldown_until - time.time()):.0f}s")
                return

            strategy_trades = [t for t in self.active_trades.values() if t['strategy'] == strategy]
            if any(t['symbol'] == symbol for t in strategy_trades):
                return
            
            max_concurrent = 3 if regime_val == 1 else 5
            if len(strategy_trades) >= max_concurrent:
                return
                
            if direction not in (1, -1):
                return
            
            if direction == 1 and not (sl < entry_price < tp):
                return
            if direction == -1 and not (tp < entry_price < sl):
                return
                
            stop_dist = abs(entry_price - sl)

            # --- TIGHT-SL FLOOR: Reject entries where SL is tighter than minimum % of price ---
            # Per-symbol minimum stop distances (wider for low-priced/high-spread assets)
            MIN_STOP_PCT = {
                'BTCUSDT': 0.001, 'ETHUSDT': 0.001, 'BNBUSDT': 0.0015,
                'SOLUSDT': 0.002, 'XRPUSDT': 0.002, 'LINKUSDT': 0.002,
                'AVAXUSDT': 0.002, 'LTCUSDT': 0.002, 'DOTUSDT': 0.002,
                'ADAUSDT': 0.003, 'NEARUSDT': 0.003, 'SUIUSDT': 0.003,
                'DOGEUSDT': 0.004, 'TRXUSDT': 0.004,
                'XAUUSDT': 0.001, 'XAGUSDT': 0.002,
                'CLUSDT': 0.003, 'NATGASUSDT': 0.005,
            }
            min_stop_pct = MIN_STOP_PCT.get(symbol, 0.003)  # Default 0.3%
            min_stop_dist = entry_price * min_stop_pct
            if stop_dist < min_stop_dist:
                print(f"[RiskGovernor] Entry blocked. {symbol} {strategy} stop distance "
                      f"{stop_dist:.6f} < min {min_stop_dist:.6f} ({min_stop_pct*100:.1f}% of price). "
                      f"Spread risk too high — skipping.")
                return

            env_risk_usd = float(os.environ.get("ENGINE_RISK_USD", str(ENGINE_RISK_USD)))
            if env_risk_usd > 0.0:
                risk_capital = env_risk_usd * risk_mult
            else:
                risk_capital = max(0.0, self.current_capital) * ENGINE_RISK_PCT * risk_mult
            
            if risk_capital <= 0.0 or stop_dist <= 0:
                return
                
            units = risk_capital / stop_dist

            # --- NOTIONAL CAP: Never open a position > $50,000 notional ---
            MAX_NOTIONAL = 50_000.0
            notional = units * entry_price
            if notional > MAX_NOTIONAL:
                units = MAX_NOTIONAL / entry_price
                print(f"[RiskGovernor] {symbol} notional capped: ${notional:.0f} -> ${MAX_NOTIONAL:.0f}")

            # 3. Overall Portfolio Open Stop Risk Check (Max 4% of current equity)
            open_stop_risk = 0.0
            for t in active_list:
                t_units = t.get('units', 0.0)
                t_dir = t.get('direction', 1)
                t_ep = t.get('entry_price', 0.0)
                t_sl = t.get('sl', 0.0)
                if t_dir == 1:
                    risk_pts = max(0.0, t_ep - t_sl)
                else:
                    risk_pts = max(0.0, t_sl - t_ep)
                open_stop_risk += t_units * risk_pts
            new_trade_risk = units * stop_dist
            total_portfolio_risk = open_stop_risk + new_trade_risk
            if total_portfolio_risk > current_equity * 0.04:
                print(f"[RiskGovernor] Entry blocked. Symbol={symbol} Strategy={strategy}. Total portfolio stop risk (${total_portfolio_risk:.2f}) exceeds 4% of equity (${current_equity * 0.04:.2f}).")
                return

            trade_id = f"{strategy}_{symbol}_{'LONG' if direction == 1 else 'SHORT'}_{int(time.time_ns())}"
            self.active_trades[trade_id] = {
                "trade_id": trade_id,
                "symbol": symbol,
                "strategy": strategy,
                "direction": direction,
                "entry_price": entry_price,
                "entry_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "entry_timestamp": time.time(),
                "sl": sl,
                "tp": tp,
                "units": units,
                "live_pnl_pct": 0.0,
                "live_pnl_usd": 0.0,
                "atr": atr,
                "macro": macro,
                "vol_regime": vol_regime,
                "sl_dist": stop_dist,
                "trail_act": trail_act,
                "trail_buf": 0.5
            }
            
            # --- MT5 Execution Dispatch ---
            mt5_res = self.mt5_broker.execute_trade(symbol, direction, entry_price, sl, tp, strategy)
            if mt5_res:
                self.active_trades[trade_id]["mt5_symbol"] = mt5_res.get("mt5_symbol")
                self.active_trades[trade_id]["mt5_ticket"] = mt5_res.get("mt5_ticket")
                self.active_trades[trade_id]["mt5_order"] = mt5_res.get("mt5_order")
                self.active_trades[trade_id]["mt5_deal"] = mt5_res.get("mt5_deal")
                self.active_trades[trade_id]["mt5_entry"] = mt5_res.get("mt5_entry")
                self.active_trades[trade_id]["mt5_sl"] = mt5_res.get("mt5_sl")
                self.active_trades[trade_id]["mt5_tp"] = mt5_res.get("mt5_tp")
                self.active_trades[trade_id]["mt5_lot"] = mt5_res.get("lot")
                if mt5_res.get("lot"):
                    self.active_trades[trade_id]["units"] = mt5_res["lot"]
                self.active_trades[trade_id]["is_pending"] = mt5_res.get("is_pending", False)
            else:
                print(f"[TradeTracker] MT5 rejected {symbol} ({strategy}) - removing phantom trade.")
                self.active_trades.pop(trade_id, None)
                return
            # ------------------------------
            
            self.save_history()

    def update_live_pnl(self, symbol: str, current_price: float, store: Optional[Any] = None) -> None:
        with self.lock:
            # 1. Update individual trade PnL
            trades_for_symbol = [t for t in self.active_trades.values() if t['symbol'] == symbol]
            for trade in trades_for_symbol:
                if trade.get("is_pending"):
                    mt5_order = trade.get("mt5_order")
                    if mt5_order and not self.mt5_broker.dry_run:
                        if not self.mt5_broker.is_order_pending(mt5_order):
                            # Resolve real position ticket (order ticket != position ticket)
                            pos_ticket = None
                            if hasattr(self.mt5_broker, "resolve_position_from_order"):
                                pos_ticket = self.mt5_broker.resolve_position_from_order(
                                    mt5_order, trade.get("mt5_symbol")
                                )
                            if pos_ticket is None and self.mt5_broker.has_position(mt5_order):
                                pos_ticket = mt5_order  # fallback
                            if pos_ticket:
                                print(f"[MT5] Pending limit order {mt5_order} for {symbol} filled -> pos={pos_ticket}. Activating trade.")
                                trade["is_pending"] = False
                                trade["mt5_ticket"] = pos_ticket
                            else:
                                print(f"[MT5] Pending limit order {mt5_order} for {symbol} was cancelled/expired. Removing phantom trade.")
                                del self.active_trades[trade["trade_id"]]
                                continue
                    elif self.mt5_broker.dry_run:
                        trade["is_pending"] = False
                    
                    if trade.get("is_pending"):
                        continue
                        
                direction = trade['direction']
                entry_price = trade['entry_price']
                pnl_pct = (current_price - entry_price) / entry_price * 100.0 if direction == 1 else (entry_price - current_price) / entry_price * 100.0
                pnl_usd = trade['units'] * (current_price - entry_price) * direction
                trade['live_pnl_pct'] = pnl_pct
                trade['live_pnl_usd'] = pnl_usd

            # 2. Run global equity drawdown breach checks (Hard Kill-Switch)
            active_list = list(self.active_trades.values())
            unrealized_pnl = sum(t.get('live_pnl_usd', 0.0) for t in active_list)
            current_equity = self.current_capital + unrealized_pnl

            daily_dd = (self.daily_start_capital - current_equity) / self.daily_start_capital * 100.0 if self.daily_start_capital > 0 else 0.0
            total_dd = (self.initial_capital - current_equity) / self.initial_capital * 100.0

            if daily_dd >= 4.5 or total_dd >= 9.0:
                if not getattr(self, 'emergency_halt', False):
                    self.emergency_halt = True
                    print(f"[RiskGovernor] [CRITICAL] EMERGENCY HALT TRIGGERED! Daily DD={daily_dd:.2f}%, Total DD={total_dd:.2f}%. Closing all active trades.")
                
                any_closed = False
                for trade in list(self.active_trades.values()):
                    trade_sym = trade['symbol']
                    if trade_sym == symbol:
                        exit_price = current_price
                    elif store is not None:
                        snap_obj = store._data.get(trade_sym)
                        exit_price = snap_obj.price if (snap_obj and snap_obj.price > 0.0) else trade['entry_price']
                    else:
                        exit_price = trade['entry_price']

                    trade['exit_price'] = exit_price
                    trade['exit_time'] = time.strftime("%Y-%m-%d %H:%M:%S")
                    trade['exit_reason'] = "EMERGENCY_HALT"
                    
                    entry_price = trade['entry_price']
                    direction = trade['direction']
                    live_pnl_pct = (exit_price - entry_price) / entry_price * 100.0 if direction == 1 else (entry_price - exit_price) / entry_price * 100.0
                    live_pnl_usd = trade['units'] * (exit_price - entry_price) * direction

                    pnl_pct = live_pnl_pct - 0.06
                    pnl_usd = live_pnl_usd - (trade['units'] * entry_price * 0.0006)
                    
                    trade['pnl_pct'] = pnl_pct
                    trade['pnl_usd'] = pnl_usd
                    
                    self.history.append(trade)
                    self.current_capital += pnl_usd
                    
                    if trade.get("mt5_ticket") and not self.mt5_broker.dry_run:
                        self._broker_submit(self.mt5_broker.close_position, trade["mt5_ticket"], "EMERGENCY_HALT")
                        
                    del self.active_trades[trade['trade_id']]
                    any_closed = True
                    
                    closed_strategy = trade.get('strategy', '')
                    for cb in self.on_close_callbacks:
                        try:
                            cb(closed_strategy, self.current_capital)
                        except Exception:
                            pass
                if any_closed:
                    self.save_history()

    def check_exits(self, symbol: str, current_price: float, current_atr_or_dict: Any = 0.0) -> None:
        with self.lock:
            trades_for_symbol = [t for t in self.active_trades.values() if t['symbol'] == symbol]
            any_closed = False
            for trade in trades_for_symbol:
                if trade.get("is_pending"):
                    continue
                direction = trade['direction']
                sl = trade['sl']
                tp = trade['tp']
                entry_price = trade['entry_price']
                
                # Resolve current ATR based on strategy if a dict is passed
                if isinstance(current_atr_or_dict, dict):
                    strategy = trade.get('strategy', STRATEGY_DISPLAY_NAME)
                    current_atr = float(current_atr_or_dict.get(strategy, 0.0) or 0.0)
                else:
                    current_atr = float(current_atr_or_dict or 0.0)
                
                # --- OOS EXACT RATCHET TRAILING STOP (run_all_6.py parity) ---
                entry_atr = trade.get('atr', 0.0)
                tp_dist = trade.get('intended_tp_dist', abs(tp - entry_price))
                trail_dist = 0.8 * entry_atr if entry_atr > 0 else (0.8 * sl_dist if sl_dist else 0.0)

                if direction == 1:
                    profit_from_entry = current_price - entry_price
                    if profit_from_entry >= tp_dist:  # ONLY activate after reaching 5.0R target
                        best_price = max(trade.get('best_price', current_price), current_price)
                        trade['best_price'] = best_price
                        new_sl = best_price - trail_dist
                        if new_sl > sl:
                            trade['sl'] = new_sl
                            sl = new_sl
                            if trade.get("mt5_ticket") and not self.mt5_broker.dry_run:
                                mt5_sl = self._translate_to_mt5_price(trade, sl)
                                mt5_tp = self._translate_to_mt5_price(trade, trade["tp"])
                                self._broker_submit(self.mt5_broker.modify_sltp, trade["mt5_symbol"], trade["mt5_ticket"], mt5_sl, mt5_tp)
                else:
                    profit_from_entry = entry_price - current_price
                    if profit_from_entry >= tp_dist:  # ONLY activate after reaching 5.0R target
                        best_price = min(trade.get('best_price', current_price), current_price)
                        trade['best_price'] = best_price
                        new_sl = best_price + trail_dist
                        if new_sl < sl:
                            trade['sl'] = new_sl
                            sl = new_sl
                            if trade.get("mt5_ticket") and not self.mt5_broker.dry_run:
                                mt5_sl = self._translate_to_mt5_price(trade, sl)
                                mt5_tp = self._translate_to_mt5_price(trade, trade["tp"])
                                self._broker_submit(self.mt5_broker.modify_sltp, trade["mt5_symbol"], trade["mt5_ticket"], mt5_sl, mt5_tp)
                
                should_close = False
                reason = ""
                
                # --- MAX_BARS Timeout Exit (Parity with agent6_exact.py) ---
                # 96 bars of 15m = 24 hours (86400 seconds)
                elapsed_time = time.time() - trade.get('entry_timestamp', time.time())
                if elapsed_time >= 86400:
                    should_close = True
                    reason = "TIMEOUT"
                
                if not should_close:
                    if direction == 1:
                        if current_price <= sl:
                            should_close = True
                            reason = "SL"
                        elif current_price >= tp:
                            should_close = True
                            reason = "TP"
                    else:
                        if current_price >= sl:
                            should_close = True
                            reason = "SL"
                        elif current_price <= tp:
                            should_close = True
                            reason = "TP"
                        
                if should_close:
                    if trade.get("closing_dispatched"):
                        continue
                        
                    exit_price = current_price
                    trade['exit_price'] = exit_price
                    trade['exit_time'] = time.strftime("%Y-%m-%d %H:%M:%S")
                    trade['exit_reason'] = reason
                    
                    entry_price = trade['entry_price']
                    pnl_pct = (exit_price - entry_price) / entry_price * 100.0 if direction == 1 else (entry_price - exit_price) / entry_price * 100.0
                    pnl_pct -= 0.06
                    
                    pnl_usd = (trade['units'] * (exit_price - entry_price) * direction) - (trade['units'] * entry_price * 0.0006)
                    
                    trade['pnl_pct'] = pnl_pct
                    trade['pnl_usd'] = pnl_usd
                    
                    if trade.get("mt5_ticket") and not self.mt5_broker.dry_run:
                        trade["closing_dispatched"] = True
                        
                        def make_close_cb(t_id, t_dict):
                            def _cb(f):
                                try:
                                    res = f.result()
                                    with self.lock:
                                        if res and t_id in self.active_trades:
                                            self.history.append(t_dict)
                                            self.current_capital += t_dict.get('pnl_usd', 0)
                                            del self.active_trades[t_id]
                                            self.save_history()
                                            
                                            try:
                                                details = self.mt5_broker.broker.get_account_details()
                                                if details and details.get("balance", 0.0) > 0.0:
                                                    self.current_capital = details["balance"]
                                            except Exception:
                                                pass
                                        elif not res and t_id in self.active_trades:
                                            print(f"[Broker] Close rejected/failed for {t_id}. Re-arming local state.")
                                            self.active_trades[t_id]["closing_dispatched"] = False
                                except Exception as e:
                                    print(f"[Broker] Exception during async close for {t_id}: {e}")
                                    with self.lock:
                                        if t_id in self.active_trades:
                                            self.active_trades[t_id]["closing_dispatched"] = False
                            return _cb
                            
                        if hasattr(self, "broker_executor") and self.broker_executor:
                            fut = self.broker_executor.submit(self.mt5_broker.close_position, trade["mt5_ticket"], reason)
                            fut.add_done_callback(make_close_cb(trade["trade_id"], trade.copy()))
                    else:
                        self.history.append(trade)
                        self.current_capital += pnl_usd
                        del self.active_trades[trade['trade_id']]
                        any_closed = True
                        
                    closed_strategy = trade.get("strategy", "")
                    cooldown_secs = self._cooldown_secs_after_close(closed_strategy, reason)
                    if cooldown_secs > 0:
                        self.reentry_cooldown_until[self._cooldown_key(closed_strategy, symbol)] = time.time() + cooldown_secs

                    for cb in self.on_close_callbacks:
                        try:
                            cb(closed_strategy, self.current_capital)
                        except Exception:
                            pass
                    
            if any_closed:
                self.save_history()

    def get_stats(self) -> dict:
        with self.lock:
            total = len(self.history)
            if total == 0:
                return {"total": 0, "winrate": 0.0, "total_pnl_usd": 0.0, "current_capital": self.current_capital}
            wins = sum(1 for t in self.history if t.get('pnl_usd', 0.0) > 0)
            total_pnl_usd = sum(t.get('pnl_usd', 0.0) for t in self.history)
            return {
                "total": total,
                "winrate": (wins / total) * 100.0,
                "total_pnl_usd": total_pnl_usd,
                "current_capital": self.current_capital
            }

    def reconcile_with_mt5(self) -> None:
        """
        Keep active_trades in absolute sync with MT5 terminal positions.
        - Drop local trades whose MT5 position is gone (broker SL/TP hit).
        - Promote filled pending orders to live tickets.
        Called periodically from the rollover watchdog (non-blocking path).
        """
        if getattr(self.mt5_broker, "dry_run", True):
            return
        with self.lock:
            try:
                broker_positions = {}
                if hasattr(self.mt5_broker, "list_engine_positions"):
                    for p in self.mt5_broker.list_engine_positions():
                        broker_positions[int(p.ticket)] = p

                stale_ids = []
                for tid, trade in list(self.active_trades.items()):
                    if trade.get("is_pending"):
                        mt5_order = trade.get("mt5_order")
                        if mt5_order and not self.mt5_broker.is_order_pending(mt5_order):
                            pos_ticket = None
                            if hasattr(self.mt5_broker, "resolve_position_from_order"):
                                pos_ticket = self.mt5_broker.resolve_position_from_order(
                                    mt5_order, trade.get("mt5_symbol")
                                )
                            if pos_ticket:
                                trade["is_pending"] = False
                                trade["mt5_ticket"] = pos_ticket
                            else:
                                stale_ids.append(tid)
                        continue

                    ticket = trade.get("mt5_ticket")
                    if not ticket:
                        continue
                    if ticket not in broker_positions and not self.mt5_broker.has_position(ticket):
                        # Broker already closed (SL/TP) — archive locally at last known price
                        trade["exit_price"] = trade.get("entry_price")
                        trade["exit_time"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        trade["exit_reason"] = "BROKER_SYNC"
                        trade["pnl_pct"] = trade.get("live_pnl_pct", 0.0) - 0.06
                        trade["pnl_usd"] = trade.get("live_pnl_usd", 0.0)
                        self.history.append(trade)
                        self.current_capital += trade.get("pnl_usd", 0.0)
                        stale_ids.append(tid)
                        print(f"[MT5 SYNC] Removed orphaned local trade {tid} (ticket={ticket})")

                for tid in stale_ids:
                    self.active_trades.pop(tid, None)
                if stale_ids:
                    self.save_history()
            except Exception as e:
                print(f"[MT5 SYNC] reconcile error: {e}")

Engine1TradeTracker = LiveTradeTracker


class SnapshotStore:
    def __init__(self, symbols: List[str], predictor=None, trade_tracker: Any = None):
        self._data: Dict[str, AssetSnapshot] = {s: AssetSnapshot(symbol=s) for s in symbols}
        self._locks = {s: asyncio.Lock() for s in symbols}
        self._seq = 0
        self.predictor = predictor
        self.trade_tracker = trade_tracker
        self._global_lock = threading.RLock()
        # Pipeline health metrics — updated by each subsystem
        self.pipeline_health: Dict[str, Any] = {
            "chrome_status": "INIT",
            "chrome_latency_ms": 0.0,
            "chrome_polls": 0,
            "chrome_last_poll_ns": 0,
            "binance_ws_status": "INIT",
            "binance_ws_url": "",
            "binance_ws_ticks": 0,
            "binance_broker_status": "INIT",
            "binance_broker_balance": 0.0,
            "binance_broker_positions": 0,
            "scraper_fps": 0.0,
            "scraper_last_parse_ns": 0,
            "footprint_status": "INIT",
            "footprint_ticks": 0,
        }

    async def update(self, symbol: str, source: str = "binance", **patch: Any) -> None:
        if symbol not in self._data:
            return
        async with self._locks[symbol]:
            cur = self._data[symbol]
            clean_patch = {}
            for k, v in patch.items():
                if not hasattr(cur, k):
                    continue
                if k in ("price", "open", "high", "low", "close"):
                    fv = finite_float_or_none(v)
                    if fv is None:
                        continue
                    if k == "price" and fv <= 0.0:
                        continue
                    clean_patch[k] = fv
                elif k in (
                    "rsi", "fut_cvd", "spot_cvd", "liq_long", "liq_short",
                    "funding", "ls_ratio", "oi", "coins_bid", "coins_ask",
                    "dollars_bid", "dollars_ask", "whale_idx",
                    "tk_buy_cnt", "tk_sell_cnt",
                ):
                    # Protect against DOM parse failures returning 0.0 overwriting
                    # valid HTTP-intercepted values. Only write 0.0 if stored is also 0.
                    fv = finite_float_or_none(v)
                    if fv is None:
                        continue
                    cur_val = getattr(cur, k, 0.0)
                    if fv == 0.0 and cur_val != 0.0:
                        continue
                    clean_patch[k] = fv
                else:
                    clean_patch[k] = v

            if not clean_patch:
                return

            self._seq += 1
            new_snap = dataclasses.replace(cur, seq=self._seq, ts_ns=time.time_ns(), **clean_patch)
            
            if self.trade_tracker:
                self.trade_tracker.update_day()

            price_updated = "price" in clean_patch
            
            if self.trade_tracker and price_updated:
                # Use ATR from the unified predictor's cached signals
                atr_dict = {}
                if self.predictor and hasattr(self.predictor, '_cached_signals'):
                    cached = self.predictor._cached_signals.get(symbol, {})
                    atr_val = cached.get('atr_val', 0.0)
                    for strat_name in SIX_STRAT_NAMES.values():
                        atr_dict[strat_name] = atr_val
                self.trade_tracker.check_exits(symbol, new_snap.price, atr_dict)
                self.trade_tracker.update_live_pnl(symbol, new_snap.price, self)
            price_fresh = price_updated and new_snap.price > 0.0
            self._data[symbol] = new_snap

            if price_fresh and self.predictor:
                def _run_ml_predictors(sym: str, snap_obj, tracker):
                    try:
                        updated_snap = self.predictor.on_tick_update(sym, snap_obj, tracker)
                        if updated_snap is not None and getattr(updated_snap, 'strategy_armed', None):
                            with self._global_lock:
                                existing = self._data.get(sym)
                                if existing:
                                    self._data[sym] = dataclasses.replace(existing, strategy_armed=updated_snap.strategy_armed)
                    except Exception as e:
                        print(f"[ML Predictor] Exception for {sym}: {e}")
                        
                # Fire and forget ML predictions so they don't block the WebSocket price stream
                asyncio.create_task(asyncio.to_thread(_run_ml_predictors, symbol, new_snap, self.trade_tracker))

    def snapshot(self) -> Dict[str, AssetSnapshot]:
        # GIL-atomic shallow copy of dict references; safe for lock-free reads
        return dict(self._data)

# --- BINANCE FOOTPRINT ENGINE ---
TICK_SIZES = {
    "BTCUSDT": 10.0,       # ~0.016% - 12-31 rows
    "ETHUSDT": 0.25,       # ~0.015% - 12-30 rows (was 0.5, too blocky)
    "XRPUSDT": 0.0002,     # ~0.018% - 11-27 rows
    "BNBUSDT": 0.05,       # ~0.009% - 23-58 rows (was 0.1)
    "SOLUSDT": 0.01,       # ~0.016% - 12-32 rows (was 0.02)
    "DOGEUSDT": 0.00002,   # ~0.024% - 8-21 rows
    "ADAUSDT": 0.00003,    # ~0.019% - 10-26 rows (was 0.00005)
    "TRXUSDT": 0.00005,    # ~0.016% - 13-32 rows
    "LINKUSDT": 0.001,     # ~0.013% - 15-38 rows (was 0.002)
    "AVAXUSDT": 0.001,     # ~0.016% - 12-32 rows (was 0.002)
    "XLMUSDT": 0.00005,    # ~0.028% - 7-18 rows
    "HBARUSDT": 0.00002,   # ~0.026% - 8-20 rows
    "LTCUSDT": 0.01,       # ~0.024% - 8-21 rows (was 0.02, critical fix)
    "DOTUSDT": 0.0002,     # ~0.021% - 9-23 rows (was 0.0005, critical fix)
    "XMRUSDT": 0.05,       # ~0.016% - 12-31 rows
    "NEARUSDT": 0.0005,    # ~0.024% - 8-21 rows
    "UNIUSDT": 0.0005,     # ~0.021% - 10-24 rows
    "FILUSDT": 0.0002,     # ~0.027% - 7-19 rows
    "SUIUSDT": 0.0005,     # Tick size for SUI
    "XAUUSDT": 0.25,       # Tick size for Gold
    "XAGUSDT": 0.002,      # Tick size for Silver
    "CLUSDT": 0.005,       # Tick size for Crude Oil
    "NATGASUSDT": 0.0002,  # Tick size for Natural Gas
}

class FootprintCandle:
    """Tracks a single 15m kline candle's delta and volume profile."""
    def __init__(self, tick_size: float):
        self.tick_size = tick_size
        self.candle_open_ms: int = 0
        self.delta: float = 0.0
        self.volume_profile: Dict[float, float] = collections.defaultdict(float)

    def _bucket(self, price: float) -> float:
        return round(price / self.tick_size) * self.tick_size

    def update(self, candle_open_ms: int, buy_vol: float, sell_vol: float, close_price: float) -> None:
        """Called with the latest kline data. Resets automatically on new candle."""
        if candle_open_ms != self.candle_open_ms:
            # New 15m candle opened — reset everything
            self.candle_open_ms = candle_open_ms
            self.delta = 0.0
            self.volume_profile.clear()
        self.delta = buy_vol - sell_vol
        # Volume profile: accumulate on close price bucket (klines don't provide tick-level data)
        bucket = self._bucket(close_price)
        self.volume_profile[bucket] = buy_vol + sell_vol

    @property
    def poc(self) -> float:
        if not self.volume_profile:
            return 0.0
        return max(self.volume_profile.items(), key=lambda kv: kv[1])[0]


class BinanceTradePriceWebSocketFeed:
    def __init__(self, symbols: List[str], store: SnapshotStore):
        self.symbols = [
            s for s in symbols
            if s not in ("XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT")
        ]
        self.store = store
        self.running = True
        self.last_heartbeat_ns = time.time_ns()
        self.last_emit_ns: Dict[str, int] = {}
        self.tab_id = "binance_ws"
        self.skip_watchdog = True  # WS may be network-blocked (ISP); REST feed covers all price needs
        
    async def run(self) -> None:
        if not self.symbols:
            return
            
        streams = "/".join(f"{s.lower()}@aggTrade" for s in self.symbols)
        url = os.environ.get("BINANCE_WS_URL", f"wss://fstream.binance.com/stream?streams={streams}")
        print(f"[Binance WS] Starting with URL: {url}")
        
        while self.running:
            try:
                # Wrap connect with timeout to prevent watchdog hangs
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    open_timeout=15,  # Prevents hanging during connection
                    max_queue=4096,
                ) as ws:
                    print("[Binance WS] Connected trade price stream.")
                    if self.store and hasattr(self.store, 'pipeline_health'):
                        self.store.pipeline_health["binance_ws_status"] = "CONNECTED"
                        self.store.pipeline_health["binance_ws_url"] = url[:60] + "..."
                    async for raw in ws:
                        if not self.running:
                            break
                            
                        self.last_heartbeat_ns = time.time_ns()
                        if self.store and hasattr(self.store, 'pipeline_health'):
                            self.store.pipeline_health["binance_ws_ticks"] += 1
                        
                        try:
                            msg = json.loads(raw)
                            data = msg.get("data", {})
                            sym = data.get("s")
                            p_str = data.get("p")
                            
                            def finite_float_or_none(v):
                                try:
                                    val = float(v)
                                    import math
                                    if math.isfinite(val): return val
                                    return None
                                except:
                                    return None

                            price = finite_float_or_none(p_str)
                            
                            if sym not in self.symbols or price is None or price <= 0:
                                continue
                                
                            # Track WebSocket message queue & processing lag
                            event_time_ms = data.get("E")
                            if event_time_ms:
                                lag_sec = (time.time() * 1000 - event_time_ms) / 1000.0
                                if lag_sec > 2.0:
                                    print(f"\n[ALERT] [LAG] WebSocket message processing lag for {sym} is {lag_sec:.2f}s!")
                                
                            now_ns = time.time_ns()
                            last_ns = self.last_emit_ns.get(sym, 0)
                            if now_ns - last_ns < 150_000_000:  # 150 ms
                                continue
                            self.last_emit_ns[sym] = now_ns
                            
                            await self.store.update(sym, source="binance_ws", price=price)
                        except Exception as inner_e:
                            continue
                            
            except Exception as e:
                if self.store and hasattr(self.store, 'pipeline_health'):
                    self.store.pipeline_health["binance_ws_status"] = "RECONNECTING"
                print(f"[Binance WS] Disconnected/error: {e}. Reconnecting in 5s...")
                await asyncio.sleep(5.0)


class BinanceFootprintFeed:
    """Polls Binance Futures klines REST API every 5s to derive 15m candle delta and POC."""
    def __init__(self, symbols: List[str], store: SnapshotStore):
        self.symbols = symbols
        self.store = store
        # Exclude commodities not on Binance Futures
        self.valid_symbols = [s for s in symbols if s not in ["XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"]]
        self.candles = {}
        for s in self.valid_symbols:
            tick = TICK_SIZES.get(s)
            if tick is None:
                raise KeyError(f"No TICK_SIZE configured for {s}; refusing to guess POC bucket.")
            self.candles[s] = FootprintCandle(tick)
        self.last_heartbeat_ns = time.time_ns()
        self.running = True
        self.consecutive_failures = 0
        self.was_failing = False

    async def run(self) -> None:
        url = "https://fapi.binance.com/fapi/v1/klines"

        async def _fetch_one(session: aiohttp.ClientSession, idx: int, sym: str) -> None:
            try:
                params = {"symbol": sym, "interval": "15m", "limit": 1}
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data:
                            item = data[-1]
                            candle_open_ms = int(item[0])
                            tot_vol = float(item[5])
                            buy_vol = float(item[9])
                            sell_vol = tot_vol - buy_vol
                            close_price = float(item[4])
                            candle = self.candles[sym]
                            candle.update(candle_open_ms, buy_vol, sell_vol, close_price)
                            await self.store.update(
                                sym,
                                source="binance",
                                price=close_price,
                                open=float(item[1]),
                                high=float(item[2]),
                                low=float(item[3]),
                                close=close_price,
                                fp_delta=candle.delta,
                                fp_poc=candle.poc
                            )
                            successes[idx] = True
            except Exception:
                pass  # individual symbol errors are covered by the outer consolidated warning

        while self.running:
            try:
                # Use ThreadedResolver to bypass asyncio resolver warnings on Windows
                connector = aiohttp.TCPConnector(
                    resolver=aiohttp.ThreadedResolver(),
                    family=socket.AF_INET,
                    keepalive_timeout=60,
                    enable_cleanup_closed=True,
                )
                # Session lives for 30 minutes before being refreshed
                session_start = time.time()
                async with aiohttp.ClientSession(connector=connector) as session:
                    while self.running and (time.time() - session_start) < 1800:
                        self.last_heartbeat_ns = time.time_ns()
                        successes = [False] * len(self.valid_symbols)
                        await asyncio.gather(*[_fetch_one(session, idx, s) for idx, s in enumerate(self.valid_symbols)])
                        
                        if any(successes):
                            if self.was_failing:
                                print("[Binance Feed] [INFO] Connection restored.")
                                self.was_failing = False
                            if self.store and hasattr(self.store, 'pipeline_health'):
                                self.store.pipeline_health["footprint_status"] = "CONNECTED"
                                self.store.pipeline_health["footprint_ticks"] += 1
                            self.consecutive_failures = 0
                        else:
                            self.consecutive_failures += 1
                            if self.consecutive_failures == 1:
                                print("[Binance Feed] [WARN] Connection issues detected (all queries failed).")
                            elif self.consecutive_failures % 30 == 0:
                                print(f"[Binance Feed] [WARN] Connection is still down (consecutive failures: {self.consecutive_failures})")
                            self.was_failing = True
                            
                        await asyncio.sleep(2.0)
            except Exception as e:
                if self.consecutive_failures <= 3:
                    print(f"[Binance Feed] [WARN] Session error: {e}. Retrying in 10s...")
                await asyncio.sleep(10.0)

# --- COINGLASS JS SHIMS ---
INIT_SCRIPT = ""

# JS run inside the TradingView iframe — extracts OHLCV and all indicator legend
SINGLE_FRAME_EXTRACTION_JS = r'''() => {
    let data = {
        volume: 'N/A',
        open_interest: 'N/A',
        funding_rate: '0.0',
        ls_ratio: 'N/A',
        futures_cvd: 'N/A',
        spot_cvd: 'N/A',
        rsi: 'N/A',
        liquidations_long: '0.0',
        liquidations_short: '0.0',
        coins_bid: 'N/A',
        coins_ask: 'N/A',
        dollars_bid: 'N/A',
        dollars_ask: 'N/A',
        whale_index: 'N/A',
        taker_buy_count: 'N/A',
        taker_sell_count: 'N/A'
    };
    let minusRe = /[\u2212\u2012\u2013\u2014]/g;
    let numRe = /^[+-]?\d+(\.\d+)?([KkMmBbTt])?%?$|^[+-]?0\.0+\d*%?$/;

    let extractNumericVals = (fullText) => {
        let cleanText = fullText.replace(minusRe, '-');
        let matches = cleanText.match(/[+-]?\d+(?:\.\d+)?(?:[KkMmBbTt])?%?/g) || [];
        return matches;
    };

    // 1. Extract Symbol & OHLC
    let seriesEl = document.querySelector('[data-name="legend-series-item"], [class*="series-"]');
    if (seriesEl) {
        let txt = (seriesEl.innerText || '').replace(minusRe, '-');
        let lines = txt.split('\n').map(s => s.trim()).filter(s => s);
        if (lines.length > 0) {
            data.symbol = lines[0].split(' ')[0].trim();
            let valTitles = Array.from(seriesEl.querySelectorAll('[class*="valueTitle-"]'));
            let valValues = Array.from(seriesEl.querySelectorAll('[class*="valueValue-"]'));
            for (let k = 0; k < valTitles.length; k++) {
                let t = valTitles[k].innerText.trim();
                let v = valValues[k] ? valValues[k].innerText.trim().replace(minusRe, '-') : '';
                if (t === 'O') data.open = v;
                else if (t === 'H') data.high = v;
                else if (t === 'L') data.low = v;
                else if (t === 'C') data.close = v;
            }
        }
    }

    // 2. Extract Indicators
    let legends = Array.from(document.querySelectorAll('[data-name="legend-source-item"], [class*="study-"], .legend-TG1_J52N, [class*="legend-"]'));
    for (let el of legends) {
        let fullText = el.innerText || '';
        if (!fullText.trim()) continue;
        let lines = fullText.split('\n').map(s => s.trim()).filter(s => s);
        if (lines.length === 0) continue;
        let title = lines[0].toLowerCase();
        let lowerText = fullText.toLowerCase();

        if (el === seriesEl || el.className.includes('series-')) continue;

        let numVals = extractNumericVals(fullText);

        if (title.includes('volume') && !title.includes('cumulative') && !title.includes('bid & ask') && !title.includes('taker')) {
            if (numVals.length > 0) data.volume = numVals[numVals.length - 1];
        } else if (title.includes('open interest') && !title.includes('funding')) {
            if (numVals.length > 0) data.open_interest = numVals[numVals.length - 1];
        } else if (title.includes('funding')) {
            for (let j = lines.length - 1; j >= 1; j--) {
                let t = lines[j].trim();
                let clean = t.replace(/,/g, '').replace(minusRe, '-').replace(/%/g, '');
                if (numRe.test(clean)) {
                    let raw = parseFloat(clean);
                    data.funding_rate = !isNaN(raw) ? (raw * 100).toFixed(4) + '%' : t;
                    break;
                }
            }
        } else if (title.includes('long/short')) {
            if (numVals.length > 0) data.ls_ratio = numVals[numVals.length - 1];
        } else if (title.includes('futures cumulative')) {
            if (numVals.length > 0) data.futures_cvd = numVals[numVals.length - 1];
        } else if (title.includes('spot cumulative')) {
            if (numVals.length > 0) data.spot_cvd = numVals[numVals.length - 1];
        } else if (title.includes('rsi')) {
            if (numVals.length > 0) {
                let rsiVal = numVals[numVals.length - 1];
                if (rsiVal !== '100.00' && rsiVal !== '0.00') data.rsi = rsiVal;
            }
        } else if (title.includes('liquidation')) {
            let liqVals = [];
            for (let j = 1; j < lines.length; j++) {
                let t = lines[j].trim();
                let clean = t.replace(/,/g, '').replace(minusRe, '-');
                if (numRe.test(clean) && clean !== '∅') {
                    liqVals.push(t);
                }
            }
            let isExplicitShort = title.includes('short') || title.includes('sell');
            let isExplicitLong = title.includes('long') || title.includes('buy');

            liqVals.forEach(valStr => {
                let cleanStr = valStr.replace(/,/g, '').replace(minusRe, '-');
                let valNum = parseFloat(cleanStr);
                if (isNaN(valNum)) return;
                
                if (isExplicitShort) {
                    data.liquidations_short = valStr;
                } else if (isExplicitLong) {
                    data.liquidations_long = valStr;
                } else {
                    if (valNum > 0) {
                        data.liquidations_long = valStr;
                    } else if (valNum < 0) {
                        data.liquidations_short = valStr;
                    } else {
                        if (!data.liquidations_long || data.liquidations_long === '0.0') data.liquidations_long = '0';
                        if (!data.liquidations_short || data.liquidations_short === '0.0') data.liquidations_short = '0';
                    }
                }
            });
        } else if (lowerText.includes('bid & ask') || lowerText.includes('taker buy/sell volume') || lowerText.includes('taker buy/sell value')) {
            if (lowerText.includes('coins') || lowerText.includes('volume')) {
                if (numVals.length >= 2) {
                    data.coins_bid = numVals[numVals.length - 2];
                    data.coins_ask = numVals[numVals.length - 1];
                }
            }
            if (lowerText.includes('dollars') || lowerText.includes('value')) {
                if (numVals.length >= 2) {
                    data.dollars_bid = numVals[numVals.length - 2];
                    data.dollars_ask = numVals[numVals.length - 1];
                }
            }
        } else if (lowerText.includes('whale index')) {
            if (numVals.length > 0) data.whale_index = numVals[numVals.length - 1];
        } else if (lowerText.includes('taker buy/sell count')) {
            if (numVals.length >= 3) {
                data.taker_buy_count = numVals[numVals.length - 3];
                data.taker_sell_count = numVals[numVals.length - 2];
            } else if (numVals.length === 2) {
                data.taker_buy_count = numVals[numVals.length - 2];
                data.taker_sell_count = numVals[numVals.length - 1];
            }
        }
    }
    
    let rawLegends = legends.map(el => el.innerText || '');
    return { success: true, data: data, rawLegends: rawLegends };
}
'''

# --- BROWSER SCRAPER PAGE CLASS ---
class CoinglassTab:
    def __init__(self, context: BrowserContext, symbols: List[str], store: SnapshotStore, tab_id: str):
        self.context = context
        self.symbols = symbols
        self.store = store
        self.tab_id = tab_id
        self.is_seeding = False
        self.page: Optional[Page] = None
        self.last_heartbeat_ns = time.time_ns()
        self.running = True
        self._response_tasks: set[asyncio.Task] = set()
        self.poll_failures = 0

    async def start(self) -> None:
        self.page = await self.context.new_page()
        
        # Suppress noisy TradingView internal console spam; only print errors and CoinGlass messages
        def _on_console(msg):
            text = msg.text
            typ = msg.type
            skip_patterns = (
                "Recurring script engine stop",
                "76 custom indicators loaded",
                "Content Security Policy",
                "WebSocket connection to",
                "ERR_NAME_NOT_RESOLVED",
                "502",
                "wss.coinglass.com",
                "net::ERR_",
                "Failed to fetch",
            )
            if any(p in text for p in skip_patterns):
                return
            if typ in ("error", "warning") or "coinglass" in text.lower():
                print(f"[{self.tab_id} CONSOLE] {typ} {text}")

        def _on_page_error(exc):
            msg = str(exc)
            # Filter generic browser resource errors that are not actionable
            if any(p in msg for p in ("unknown compression", "net::", "ERR_", "Failed to fetch", "ResizeObserver", "reading 'symbol'")):
                return
            print(f"[{self.tab_id} PAGE ERROR] {msg}")

        self.page.on("console", _on_console)
        self.page.on("pageerror", _on_page_error)
        
        # Intercept HTTP API responses natively to capture Open Interest and Funding Rates securely
        # without introducing compression encoding errors on the page.
        async def handle_response(response):
            try:
                url = response.url
                if any(k in url for k in ("open-interest", "funding-rate", "liquidation", "long-short", "rsi", "cumulative-volume")):
                    body = await response.text()
                    await self._route_payload({"url": url, "body": body})
            except Exception:
                pass

        def _spawn_response_task(response):
            task = asyncio.create_task(handle_response(response))
            self._response_tasks.add(task)
            task.add_done_callback(self._response_tasks.discard)

        self.page.on("response", _spawn_response_task)
        
        print(f"[{self.tab_id}] Opening layout: {URL}...")
        await self.page.goto(URL, wait_until="load", timeout=45000)
        print(f"[{self.tab_id}] Waiting 15 seconds for layout to load...")
        await asyncio.sleep(15)  # Wait 15 seconds for S9 chart renders

    async def reconnect(self, focus_lock: asyncio.Lock) -> None:
        print(f"[{self.tab_id}] [RECOVERY] Attempting to reconnect/restart the tab...")
        self.is_seeding = True
        try:
            self.running = False
            if self.page:
                try:
                    await self.page.close()
                except Exception:
                    pass
            self.running = True
            await self.start()
            await self.inject_and_configure_all(focus_lock)
            print(f"[{self.tab_id}] [RECOVERY] Tab successfully restarted and re-configured.")
            self.last_heartbeat_ns = time.time_ns()
        except Exception as e:
            print(f"[{self.tab_id}] [RECOVERY ERROR] Failed to restart tab: {e}")
        finally:
            self.is_seeding = False

    async def inject_and_configure_all(self, focus_lock: asyncio.Lock):
        """Programmatic JS-based S9 indicator & symbol configuration"""
        print(f"[{self.tab_id}] Bringing tab to front...")
        await self.page.bring_to_front()
        await asyncio.sleep(0.5)
        
        # Wait for layout containers to render fully
        try:
            print(f"[{self.tab_id}] Waiting for layout containers to render...")
            await self.page.wait_for_selector("#tv_chart_container_win1, #tv_chart_container_main", state="attached", timeout=30000)
            await self.page.wait_for_selector("#tv_chart_container_win9", state="attached", timeout=30000)
            await asyncio.sleep(2.0)
        except Exception as e:
            print(f"[{self.tab_id}] [WARN] Timeout waiting for layout containers: {e}")

        print(f"[{self.tab_id}] Configuring symbols and indicators on grid layout via JS API...")
        for win_idx, symbol in enumerate(self.symbols, start=1):
            print(f"[{self.tab_id}] [Config] Configuring window {win_idx}/9 for {symbol}")
            container_id = f"tv_chart_container_win{win_idx}"
            selector = f"#{container_id}" if win_idx != 1 else f"#{container_id}, #tv_chart_container_main"
            container = self.page.locator(selector).first
            
            if await container.count() > 0:
                try:
                    iframe = container.locator("iframe").first
                    await iframe.wait_for(state="attached", timeout=15000)
                    iframe_handle = await iframe.element_handle(timeout=15000)
                    if iframe_handle:
                        frame = await iframe_handle.content_frame()
                        if frame:
                            # Evaluate programmatic setup script inside the iframe
                            res = await frame.evaluate(f'''async () => {{
                                try {{
                                    // 1. Wait for TradingView API and CoinGlass custom studies metadata cache to load
                                    let apiReady = false;
                                    for (let i = 0; i < 40; i++) {{
                                        if (typeof tradingViewApi !== 'undefined' && 
                                            tradingViewApi.activeChart && 
                                            tradingViewApi._chartApiInstance && 
                                            tradingViewApi._chartApiInstance._studyEngine && 
                                            tradingViewApi._chartApiInstance._studyEngine._metainfoCache) {{
                                            
                                            let cache = tradingViewApi._chartApiInstance._studyEngine._metainfoCache;
                                            let keys = Object.keys(cache);
                                            if (keys.some(k => cache[k].description && cache[k].description.includes('CoinGlass'))) {{
                                                apiReady = true;
                                                break;
                                            }}
                                        }}
                                        await new Promise(r => setTimeout(r, 500));
                                    }}
                                    
                                    if (!apiReady) {{
                                        return {{ success: false, error: 'CoinGlass indicator metadata cache not ready' }};
                                    }}
                                    
                                    // 2. Set Symbol
                                    tradingViewApi.changeSymbol("Binance_{symbol}");
                                    
                                    // 3. Set Timeframe to 15m
                                    if (typeof chartWidgetCollection !== 'undefined') {{
                                        chartWidgetCollection.setResolution('15');
                                    }}
                                    
                                    // 4. Scan and inject missing indicators
                                    let ac = tradingViewApi.activeChart();
                                    if (ac) {{
                                         let existing = [];
                                         try {{
                                             existing = ac.getAllStudies() || [];
                                         }} catch (err) {{}}
                                         
                                         let hasVolume = existing.some(s => s.name && s.name.includes('Volume') && !s.name.includes('Delta'));
                                         let hasFutCVD = existing.some(s => s.name && s.name.includes('Futures Cumulative Volume Delta'));
                                         let hasSpotCVD = existing.some(s => s.name && s.name.includes('Spot Cumulative Volume Delta'));
                                         let hasRSI = existing.some(s => s.name && s.name.includes('Relative Strength Index'));
                                         let hasFunding = existing.some(s => s.name && s.name.includes('Funding Rates'));
                                         let hasLiq = existing.some(s => s.name && s.name.includes('Aggregated Liquidations'));
                                         let hasLS = existing.some(s => s.name && s.name.includes('Long/Short Ratio'));
                                         let hasOI = existing.some(s => s.name && s.name.includes('Open Interest'));
                                         let hasWhale = existing.some(s => s.name && s.name.includes('Whale Index'));
                                         let hasTaker = existing.some(s => s.name && s.name.includes('Taker Buy/Sell Count'));
                                         
                                         let bidAsks = existing.filter(s => s.name && s.name.includes('Bid & Ask'));
                                         
                                         let injectedAny = false;
                                         if (!hasVolume) {{ ac.createStudy('Volume', false, false); injectedAny = true; }}
                                         if (!hasFutCVD) {{ ac.createStudy('<CoinGlass> Aggregated Futures Cumulative Volume Delta (CVD)', false, false); injectedAny = true; }}
                                         if (!hasSpotCVD) {{ ac.createStudy('<CoinGlass> Aggregated Spot Cumulative Volume Delta (CVD)', false, false); injectedAny = true; }}
                                         if (!hasRSI) {{ ac.createStudy('Relative Strength Index', false, false); injectedAny = true; }}
                                         if (!hasFunding) {{ ac.createStudy('<CoinGlass> Funding Rates(Open Interest Weighted,Candles)', false, false); injectedAny = true; }}
                                         if (!hasLiq) {{ ac.createStudy('<CoinGlass> Aggregated Liquidations ', false, false); injectedAny = true; }}
                                         if (!hasLS) {{ ac.createStudy('<CoinGlass> Long/Short Ratio (Accounts)', false, false); injectedAny = true; }}
                                         if (!hasOI) {{ ac.createStudy('<CoinGlass> Aggregated Open Interest(STABLECOIN-margined,Candles)', false, false); injectedAny = true; }}
                                         if (!hasWhale) {{ ac.createStudy('<CoinGlass> Whale Index', false, false); injectedAny = true; }}
                                         if (!hasTaker) {{ ac.createStudy('<CoinGlass> Taker Buy/Sell Count', false, false); injectedAny = true; }}
                                         
                                         if (bidAsks.length < 2) {{
                                             for (let b of bidAsks) {{
                                                 try {{ ac.removeStudy(b.id); }} catch(e) {{}}
                                             }}
                                             ac.createStudy('<CoinGlass> Aggregated Futures Bid & Ask ', false, false, {{ "Depth": 1, "symbol": "Main chart symbol", "Measure": "Coins" }});
                                             ac.createStudy('<CoinGlass> Aggregated Futures Bid & Ask ', false, false, {{ "Depth": 1, "symbol": "Main chart symbol", "Measure": "Dollars" }});
                                             injectedAny = true;
                                         }}
                                         
                                         // Force save layout if anything was injected
                                         if (injectedAny && tradingViewApi._saveChartService && typeof tradingViewApi._saveChartService.saveChart === 'function') {{
                                             try {{
                                                 tradingViewApi._saveChartService.saveChart();
                                             }} catch(se) {{}}
                                         }}
                                         
                                         let dump = ac.getAllStudies().map(s => ({{id: s.id, name: s.name}}));
                                         return {{ success: true, dump: dump }};
                                    }}
                                    return {{ success: false, error: 'Active chart not found' }};
                                }} catch (e) {{
                                    return {{ success: false, error: e.message }};
                                }}
                            }}''')
                            if res and "dump" in res:
                                try:
                                    with open(os.path.join(base_dir, "Seeding", f"studies_{self.tab_id}_{symbol}.json"), "w") as f:
                                        json.dump(res["dump"], f, indent=2)
                                except Exception: pass
                                
                            if not res or not res.get("success"):
                                print(f"[{self.tab_id}] [WARN] Programmatic setup failed for {symbol}: {res.get('error') if res else 'Unknown'}")
                            else:
                                print(f"[{self.tab_id}] [Config] Symbol & Indicators verified/configured for {symbol}")
                except Exception as e:
                    print(f"[{self.tab_id}] [WARN] Error configuring window {win_idx} for {symbol}: {e}")
            await asyncio.sleep(0.1)

        # Wait for studies to load data from network
        print(f"[{self.tab_id}] Waiting 15 seconds for TradingView studies to load historical data...")
        await asyncio.sleep(15.0)

        try:
            await self.page.screenshot(path=os.path.join(base_dir, "Seeding", f"{self.tab_id}_layout.png"))
        except Exception as e:
            print(f"[{self.tab_id}] [WARN] Screenshot failed: {e}")
        print(f"[{self.tab_id}] Setup & Indicator injection complete.")

    async def poll_loop(self) -> None:
        """Background data poller extracting DOM legend values & JS shims"""
        async def _fetch_frame(win_idx: int) -> bool:
            sym = self.symbols[win_idx - 1]
            container_id = f"tv_chart_container_win{win_idx}"
            selector = f"#{container_id}" if win_idx != 1 else f"#{container_id}, #tv_chart_container_main"
            container = self.page.locator(selector).first
            
            if await container.count() > 0:
                iframe = container.locator("iframe").first
                if await iframe.count() > 0:
                    iframe_handle = await iframe.element_handle(timeout=10000)
                    frame = await iframe_handle.content_frame() if iframe_handle else None
                    if frame:
                        try:
                            res = await frame.evaluate(SINGLE_FRAME_EXTRACTION_JS)
                        except Exception as eval_exc:
                            print(f"[{self.tab_id}] [POLL ERROR] {sym} frame eval: {eval_exc}")
                            return False
                        if res and res.get("success"):
                            d = res["data"]
                            sym_actual = (d.get("symbol") or "").strip().upper()
                            # Check actual extracted symbol matches what we expect
                            if sym_actual and sym_actual in self.symbols:
                                target_sym = sym_actual
                            else:
                                target_sym = sym
                                
                            price_val = parse_float(d.get("close") or d.get("price") or 0.0)
                            rsi_val = parse_float(d.get("rsi", 0.0))
                            if rsi_val in (100.0, 0.0):
                                rsi_val = self.store._data.get(target_sym, AssetSnapshot(symbol=target_sym)).rsi
                            await self.store.update(
                                target_sym,
                                source="coinglass",
                                price=price_val,
                                volume=parse_float(d.get("volume", 0.0)),
                                rsi=rsi_val,
                                fut_cvd=parse_float(d.get("futures_cvd", 0.0)),
                                spot_cvd=parse_float(d.get("spot_cvd", 0.0)),
                                funding=parse_float(d.get("funding_rate", 0.0)),
                                liq_long=parse_float(d.get("liquidations_long", 0.0)),
                                liq_short=parse_float(d.get("liquidations_short", 0.0)),
                                ls_ratio=parse_float(d.get("ls_ratio", 0.0)),
                                oi=parse_float(d.get("open_interest", 0.0)),
                                coins_bid=parse_float(d.get("coins_bid", 0.0)),
                                coins_ask=parse_float(d.get("coins_ask", 0.0)),
                                dollars_bid=parse_float(d.get("dollars_bid", 0.0)),
                                dollars_ask=parse_float(d.get("dollars_ask", 0.0)),
                                whale_idx=parse_float(d.get("whale_index", 0.0)),
                                tk_buy_cnt=parse_float(d.get("taker_buy_count", 0.0)),
                                tk_sell_cnt=parse_float(d.get("taker_sell_count", 0.0))
                            )
                            return True
            return False

        while self.running:
            try:
                results = await asyncio.gather(*[_fetch_frame(i) for i in range(1, 10)], return_exceptions=True)
                has_success = False
                for r in results:
                    if isinstance(r, Exception):
                        print(f"[{self.tab_id}] [POLL ERROR] Subtask failed: {r}")
                        self.poll_failures += 1
                    elif r is True:
                        has_success = True

                if has_success:
                    self.last_heartbeat_ns = time.time_ns()
                    self.poll_failures = 0
                    if self.store and hasattr(self.store, 'pipeline_health'):
                        now_ns = time.time_ns()
                        self.store.pipeline_health["chrome_polls"] = self.store.pipeline_health.get("chrome_polls", 0) + 1
                        self.store.pipeline_health["chrome_status"] = "CONNECTED"
                        self.store.pipeline_health["chrome_latency_ms"] = 45.0
                        self.store.pipeline_health["scraper_last_parse_ns"] = now_ns
                        self.store.pipeline_health["scraper_fps"] = 2.0
                else:
                    self.poll_failures += 1
            except Exception as e:
                print(f"[{self.tab_id}] [POLL ERROR] Outer: {e}")
                self.poll_failures += 1
            
            if self.poll_failures > 5:
                print(f"[{self.tab_id}] [WATCHDOG] Max failures exceeded ({self.poll_failures}). Auto-healing by reloading page...")
                try:
                    await self.page.reload(wait_until="load", timeout=30000)
                    self.poll_failures = 0
                except Exception as ex:
                    print(f"[{self.tab_id}] [WATCHDOG] Failed to reload page: {ex}")
                    self.poll_failures = 0

            await asyncio.sleep(0.5)

    async def _route_payload(self, entry: dict) -> None:
        url = entry.get("url", "")
        body = entry.get("body", "")
        try:
            payload = json.loads(body)
        except Exception:
            return
        
        # Route to appropriate update target
        if "open-interest" in url:
            await self._apply(payload, "oi")
        elif "funding-rate" in url:
            await self._apply(payload, "funding")
        elif "liquidation" in url:
            await self._apply_liq(payload)
        elif "long-short" in url:
            await self._apply(payload, "ls_ratio")
        elif "cumulative-volume" in url:
            if "futures" in url:
                await self._apply(payload, "fut_cvd")
            else:
                await self._apply(payload, "spot_cvd")
        elif "rsi" in url:
            await self._apply(payload, "rsi")

    async def _apply(self, payload: Any, field_name: str) -> None:
        data = payload.get("data", [])
        if isinstance(data, list):
            for row in data:
                sym = row.get("symbol")
                if sym in self.symbols:
                    val = parse_float(row.get("value", 0.0))
                    await self.store.update(sym, source="coinglass", **{field_name: val})
        elif isinstance(data, dict):
            for sym, val in data.items():
                if sym in self.symbols:
                    await self.store.update(sym, source="coinglass", **{field_name: parse_float(val)})

    async def _apply_liq(self, payload: Any) -> None:
        data = payload.get("data", [])
        if isinstance(data, list):
            for row in data:
                sym = row.get("symbol")
                if sym in self.symbols:
                    long_liq = parse_float(row.get("longLiq", 0.0))
                    short_liq = parse_float(row.get("shortLiq", 0.0))
                    await self.store.update(sym, source="coinglass", liq_long=long_liq, liq_short=short_liq)

    async def seed_symbol(self, symbol: str, excel_executor, focus_lock: asyncio.Lock) -> None:
        """Performs visual backward walk to collect 50 candles and export to Excel"""
        self.is_seeding = True
        win_idx = self.symbols.index(symbol) + 1
        container_id = f"tv_chart_container_win{win_idx}"
        selector = f"#{container_id}" if win_idx != 1 else f"#{container_id}, #tv_chart_container_main"
        container = self.page.locator(selector).first
        
        async with focus_lock:
            print(f"[{self.tab_id}] Seeding {symbol} in Window {win_idx}. Acquired focus lock. Bringing tab to front...")
            await self.page.bring_to_front()
            await asyncio.sleep(0.5)
            
            iframe = container.locator("iframe").first
            try:
                await iframe.wait_for(state="attached", timeout=15000)
            except Exception:
                pass
            iframe_handle = await iframe.element_handle(timeout=10000)
            if not iframe_handle:
                print(f"[{self.tab_id}] [ERROR] No iframe handle for seeding {symbol}")
                return
            frame = await iframe_handle.content_frame()
            if not frame:
                print(f"[{self.tab_id}] [ERROR] Content frame missing for seeding {symbol}")
                return
                
            # Resolve the first canvas inside the frame
            canvas = frame.locator("canvas").first
            try:
                await canvas.wait_for(state="visible", timeout=5000)
            except Exception:
                print(f"[{self.tab_id}] [ERROR] Canvas element not visible for {symbol}")
                return
                
            # Click canvas center to focus TradingView inner context
            await canvas.click(force=True, timeout=5000)
            await asyncio.sleep(0.3)
            
            # Explicitly focus the window/document body
            await frame.evaluate("() => { window.focus(); if (document.body) document.body.focus(); }")
            await asyncio.sleep(0.2)
            
            # Press Escape to close any potential dialogs
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.2)
            
            # Reset visual using Alt+r
            await self.page.keyboard.press("Alt+r")
            await asyncio.sleep(1.0)
            
            # Wait for canvas to become visible/attached again after chart reset
            try:
                await canvas.wait_for(state="visible", timeout=5000)
            except Exception:
                pass
            
            # Right-click canvas to open context menu (forces browser focus delegation)
            await canvas.click(button="right", force=True, timeout=5000)
            await asyncio.sleep(0.5)
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.2)
            
            # Wait up to 10 seconds for indicators to load historical data from network
            print(f"[{self.tab_id}] waiting for indicators to populate historical data for {symbol}...")
            for attempt in range(20):
                res = await frame.evaluate(SINGLE_FRAME_EXTRACTION_JS)
                if res and res.get("success"):
                    d = res["data"]
                    if (d.get("volume") not in ("N/A", "0", None) and
                        d.get("rsi") not in ("N/A", "100.00", None) and
                        d.get("futures_cvd") != "N/A" and
                        d.get("spot_cvd") != "N/A" and
                        d.get("open_interest") != "N/A"):
                        print(f"[{self.tab_id}] Indicators populated in {attempt * 0.5:.1f}s")
                        break
                await asyncio.sleep(0.5)

            rect = await canvas.bounding_box()
            if not rect:
                print(f"[{self.tab_id}] [ERROR] Cannot get canvas bounding box for {symbol}")
                return

            x_pos = rect["x"] + rect["width"] - 60
            y_pos = rect["y"] + rect["height"] * 0.5

            # Hover and click to focus on the rightmost section of the canvas
            await self.page.mouse.move(x_pos, y_pos)
            await self.page.mouse.click(x_pos, y_pos)
            await asyncio.sleep(0.2)

            # ArrowLeft snaps crosshair to the latest candle
            await self.page.keyboard.press("ArrowLeft")
            await asyncio.sleep(0.3)

            # --- Dynamic Gap Calculation ---
            target_steps = 850
            existing_rows = []
            base_dir = os.path.dirname(os.path.abspath(__file__))
            combined_path = os.path.join(base_dir, "Seeding", "combined_seed_history.xlsx")
            if os.path.exists(combined_path):
                import pandas as pd
                try:
                    df = pd.read_excel(combined_path, sheet_name=symbol)
                    if not df.empty and "open_time" in df.columns:
                        existing_rows = df.to_dict('records')
                        
                        # Handle potential datetime vs int vs str timestamp differences
                        for r in existing_rows:
                            val = r.get("open_time")
                            if hasattr(val, "timestamp"):
                                from datetime import timezone
                                r["open_time"] = int(val.replace(tzinfo=timezone.utc).timestamp())
                            elif isinstance(val, (int, float)):
                                r["open_time"] = int(val)
                            elif isinstance(val, str):
                                try:
                                    val_clean = val.replace(" IST", "").strip()
                                    dt = pd.to_datetime(val_clean)
                                    from datetime import timedelta
                                    dt_utc = dt - timedelta(hours=5, minutes=30)
                                    r["open_time"] = int(dt_utc.timestamp())
                                except Exception:
                                    try:
                                        r["open_time"] = int(float(val))
                                    except Exception:
                                        pass
                        
                        # Filter out invalid open_times for max calc
                        valid_times = [r["open_time"] for r in existing_rows if isinstance(r.get("open_time"), int)]
                        if valid_times:
                            latest_time = max(valid_times)
                            current_time = int((time.time() // 900) * 900)
                            gap_candles = calculate_commodity_gap(symbol, latest_time, current_time)
                            existing_count = len(existing_rows)
                            
                            if existing_count + gap_candles >= 850:
                                target_steps = min(gap_candles + 2, 850)
                            else:
                                target_steps = 850
                                
                            print(f"\n==================================================")
                            print(f"[{self.tab_id}] {symbol} SEEDING DATABASE CHECK:")
                            print(f"[{self.tab_id}] Database has {existing_count} candles.")
                            print(f"[{self.tab_id}] Gap from offline time: {gap_candles} missing candles (calendar adjusted).")
                            print(f"[{self.tab_id}] -> WILL SCRAPE {target_steps} CANDLES NOW TO WARM UP.")
                            print(f"==================================================\n")
                        else:
                            print(f"\n==================================================")
                            print(f"[{self.tab_id}] {symbol} Found Excel sheet but no valid `open_time` ints parsed.")
                            print(f"[{self.tab_id}] -> WILL SCRAPE {target_steps} CANDLES NOW TO WARM UP.")
                            print(f"==================================================\n")
                except Exception as e:
                    print(f"[{self.tab_id}] [WARN] Could not read existing seed for {symbol}: {e}")
            else:
                print(f"\n==================================================")
                print(f"[{self.tab_id}] {symbol} No existing seed history found in Excel.")
                print(f"[{self.tab_id}] -> WILL SCRAPE {target_steps} CANDLES NOW TO WARM UP.")
                print(f"==================================================\n")
            # -------------------------------

            candles = collections.deque(maxlen=1000)
            stalls = 0
            debug_dicts = []
            
            last_key = None
            is_crypto = symbol not in ["XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"]
            
            computed_timestamps = get_historical_timestamps(symbol, int((time.time() // 900) * 900), target_steps)

            for step in range(target_steps * 2):
                if len(candles) >= target_steps:
                    print(f"[{self.tab_id}] {symbol} Reached target {target_steps} candles. Stopping walk.")
                    break
                    
                if step % 20 == 0:
                    print(f"[{self.tab_id}] Seeding {symbol}: candle {len(candles)}/{target_steps}...")
                
                # 1. Wait for DOM to update after moving crosshair (avoid duplicate read stalls)
                d = None
                for attempt in range(6):
                    res = await frame.evaluate(SINGLE_FRAME_EXTRACTION_JS)
                    if res and res.get("success"):
                        temp_d = res["data"]
                        close = parse_float(temp_d.get("close", temp_d.get("price", 0.0)))
                        volume = parse_float(temp_d.get("volume", 0.0))
                        rsi = parse_float(temp_d.get("rsi", 50.0))
                        val_key = (close, volume, rsi)
                        
                        if val_key != last_key:
                            d = temp_d
                            last_key = val_key
                            break
                    await asyncio.sleep(0.04)

                if d is None:
                    stalls += 1
                    if stalls > 4:
                        print(f"[{self.tab_id}] [WARN] Seeding stalled for {symbol} at step {step}. Ending early.")
                        break
                    # Recover visual focus delegation
                    await canvas.focus()
                    await asyncio.sleep(0.05)
                    await self.page.keyboard.press("ArrowLeft")
                    await asyncio.sleep(0.1)
                    continue
                
                stalls = 0
                
                # 2. Wait up to 600ms for lazy-loaded indicators (CVD, OI) to populate if they are currently N/A
                if is_crypto:
                    for load_attempt in range(4):
                        if (d.get("futures_cvd") != "N/A" and 
                            d.get("spot_cvd") != "N/A" and 
                            d.get("open_interest") != "N/A"):
                            break
                        await asyncio.sleep(0.15)
                        res = await frame.evaluate(SINGLE_FRAME_EXTRACTION_JS)
                        if res and res.get("success"):
                            d = res["data"]
                            
                if symbol == "BTCUSDT":
                    debug_dicts.append({
                        "step": step,
                        "data": d,
                        "rawLegends": res.get("rawLegends", []) if res else []
                    })
                    
                candle_data = {
                    "open_time": computed_timestamps[len(candles)],
                    "open":       parse_float(d.get("open",   0.0)),
                    "high":       parse_float(d.get("high",   0.0)),
                    "low":        parse_float(d.get("low",    0.0)),
                    "close":      parse_float(d.get("close",  d.get("price", 0.0))),
                    "volume":     parse_float(d.get("volume", 0.0)),
                    "rsi":        parse_float(d.get("rsi",    50.0)),
                    "fut_cvd":    parse_float(d.get("futures_cvd",      0.0)),
                    "spot_cvd":   parse_float(d.get("spot_cvd",         0.0)),
                    "funding":    parse_float(d.get("funding_rate",      0.0)),
                    "liq_long":   abs(parse_float(d.get("liquidations_long",  0.0))),
                    "liq_short":  abs(parse_float(d.get("liquidations_short", 0.0))),
                    "ls_ratio":   parse_float(d.get("ls_ratio",           1.0)),
                    "oi":         parse_float(d.get("open_interest",      0.0)),
                    "coins_bid":  parse_float(d.get("coins_bid", 0.0)),
                    "coins_ask":  parse_float(d.get("coins_ask", 0.0)),
                    "dollars_bid": parse_float(d.get("dollars_bid", 0.0)),
                    "dollars_ask": parse_float(d.get("dollars_ask", 0.0)),
                    "whale_idx":  parse_float(d.get("whale_index", 0.0)),
                    "tk_buy_cnt": parse_float(d.get("taker_buy_count", 0.0)),
                    "tk_sell_cnt": parse_float(d.get("taker_sell_count", 0.0)),
                }
                
                candles.appendleft(candle_data)
                
                # Step left — move crosshair one candle back
                await self.page.keyboard.press("ArrowLeft")
                await asyncio.sleep(0.08)

            # Restore view
            await self.page.keyboard.press("Alt+r")
            await asyncio.sleep(0.5)

            scraped_list = list(candles)
            final_list = scraped_list
            if existing_rows:
                all_data = existing_rows + scraped_list
                # Deduplicate by open_time, keeping newest (scraped over existing due to order)
                dedup = {r["open_time"]: r for r in all_data if isinstance(r.get("open_time"), int)}
                sorted_vals = sorted(dedup.values(), key=lambda x: x["open_time"])
                final_list = sorted_vals

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(excel_executor, _dump_xlsx, symbol, final_list)
            
            if self.store.predictor:
                self.store.predictor.set_history(symbol, final_list)
            
            if candles:
                last = list(candles)[-1]
                missing = [k for k, v in last.items() if v == 0.0 and k not in ("liq_long", "liq_short")]
                if missing:
                    print(f"[{self.tab_id}] [WARN] {symbol}: zero fields = {missing}")
                else:
                    print(f"[{self.tab_id}] [OK]   {symbol}: all fields populated (close={last['close']}, vol={last['volume']}, funding={last['funding']})")
                    
            if symbol == "BTCUSDT":
                try:
                    with open(os.path.join(base_dir, "Seeding", "seeding_debug_BTCUSDT.json"), "w", encoding="utf-8") as f:
                        json.dump(debug_dicts, f, indent=2)
                    await self.page.screenshot(path=os.path.join(base_dir, "Seeding", f"diag_{self.tab_id}_{symbol}.png"), clip={"x": 0, "y": 0, "width": 600, "height": 400})
                except Exception:
                    pass
            print(f"[{self.tab_id}] [Success] Seeded {symbol} with {len(candles)} candles.")

def fetch_binance_funding_rates(symbol: str) -> List[Dict[str, Any]]:
    import urllib.request
    import json
    url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit=100"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"[Binance API] Failed to fetch funding rate for {symbol}: {e}")
        return []

def fetch_binance_open_interest(symbol: str) -> List[Dict[str, Any]]:
    import urllib.request
    import json
    url = f"https://fapi.binance.com/fapi/v1/openInterestHist?symbol={symbol}&period=15m&limit=120"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"[Binance API] Failed to fetch open interest for {symbol}: {e}")
        return []

def fetch_binance_ls_ratio(symbol: str) -> List[Dict[str, Any]]:
    import urllib.request
    import json
    url = f"https://fapi.binance.com/data/globalLongShortAccountRatio?symbol={symbol}&period=15m&limit=120"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print(f"[Binance API] Failed to fetch long/short ratio for {symbol}: {e}")
        return []

def _dump_xlsx(symbol: str, rows: List[Dict[str, Any]]) -> None:
    crypto_symbols = {
        "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", 
        "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT", 
        "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT"
    }
    
    if rows and symbol in crypto_symbols:
        # 1. Backfill funding rate if all zeros
        if all(r.get("funding", 0.0) == 0.0 for r in rows):
            api_rates = fetch_binance_funding_rates(symbol)
            if api_rates:
                api_rates.sort(key=lambda x: x["fundingTime"])
                for r in rows:
                    row_time_ms = r.get("open_time", 0) * 1000
                    matching_rate = 0.0
                    for item in api_rates:
                        if item["fundingTime"] <= row_time_ms:
                            matching_rate = float(item["fundingRate"])
                        else:
                            break
                    r["funding"] = matching_rate

        # 2. Backfill open interest if all zeros
        if all(r.get("oi", 0.0) == 0.0 for r in rows):
            api_oi = fetch_binance_open_interest(symbol)
            if api_oi:
                api_oi.sort(key=lambda x: x["timestamp"])
                for r in rows:
                    row_time_ms = r.get("open_time", 0) * 1000
                    matching_oi = 0.0
                    for item in api_oi:
                        if item["timestamp"] <= row_time_ms:
                            matching_oi = float(item["sumOpenInterest"])
                        else:
                            break
                    r["oi"] = matching_oi

        # 3. Backfill long/short ratio if all zeros/default
        if all(r.get("ls_ratio", 1.0) == 1.0 or r.get("ls_ratio", 1.0) == 0.0 for r in rows):
            api_ls = fetch_binance_ls_ratio(symbol)
            if api_ls:
                api_ls.sort(key=lambda x: x["timestamp"])
                for r in rows:
                    row_time_ms = r.get("open_time", 0) * 1000
                    matching_ls = 1.0
                    for item in api_ls:
                        if item["timestamp"] <= row_time_ms:
                            matching_ls = float(item["longShortRatio"])
                        else:
                            break
                    r["ls_ratio"] = matching_ls

    # 4. Apply general forward-fill and backward-fill for all numeric columns to handle scattered zeros
    if rows:
        fill_fields = [
            "open", "high", "low", "close", "volume", "rsi", "fut_cvd", "spot_cvd", "funding", "ls_ratio", "oi",
            "coins_bid", "coins_ask", "dollars_bid", "dollars_ask", "whale_idx", "tk_buy_cnt", "tk_sell_cnt"
        ]
        for field in fill_fields:
            non_zero_vals = [r.get(field, 0.0) for r in rows if r.get(field, 0.0) != 0.0]
            if non_zero_vals:
                # Forward fill
                last_val = non_zero_vals[0]
                for r in rows:
                    val = r.get(field, 0.0)
                    if val != 0.0:
                        last_val = val
                    else:
                        r[field] = last_val
                # Backward fill
                last_val = non_zero_vals[-1]
                for r in reversed(rows):
                    val = r.get(field, 0.0)
                    if val != 0.0:
                        last_val = val
                    else:
                        r[field] = last_val

    wb = Workbook()
    ws = wb.active
    ws.title = symbol[:31]
    
    headers = [
        "open_time", "open", "high", "low", "close", "volume", 
        "rsi", "fut_cvd", "spot_cvd", "funding", "liq_long", "liq_short", "ls_ratio", "oi",
        "coins_bid", "coins_ask", "dollars_bid", "dollars_ask", "whale_idx", "tk_buy_cnt", "tk_sell_cnt"
    ]
    
    HDR_FILL = PatternFill("solid", fgColor="1F3864")
    HDR_FONT = Font(bold=True, color="FFFFFF", name="Calibri", size=11)
    CENTER = Alignment(horizontal="center", vertical="center")
    thin = Side(style="thin", color="D9D9D9")
    BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
    
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = CENTER
        cell.border = BORDER
        
    for row_idx, r in enumerate(rows, start=2):
        row_vals = []
        for h in headers:
            val = r.get(h, "")
            if h == "open_time" and isinstance(val, (int, float)):
                from datetime import datetime, timezone, timedelta
                tz_ist = timezone(timedelta(hours=5, minutes=30))
                val = datetime.fromtimestamp(val, tz=tz_ist).strftime("%Y-%m-%d %H:%M:%S IST")
            row_vals.append(val)
        ws.append(row_vals)
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.alignment = CENTER
            cell.border = BORDER
            
    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        col_letter = get_column_letter(col[0].column)
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)
        
    os.makedirs(os.path.join(base_dir, "Seeding"), exist_ok=True)
    filename = os.path.join(base_dir, "Seeding", f"{symbol}_seed_history.xlsx")
    try:
        wb.save(filename)
    except PermissionError:
        import random
        alt_filename = os.path.join(base_dir, "Seeding", f"{symbol}_seed_history_{random.randint(1000, 9999)}.xlsx")
        print(f"[WARN] Permission denied on {filename} (probably open in Excel). Saving to {alt_filename} instead.")
        try:
            wb.save(alt_filename)
        except Exception as e:
            print(f"[ERROR] Failed to save fallback Excel for {symbol}: {e}")

# --- PIPELINE STATUS HEADER ---
def render_pipeline_status(store: 'SnapshotStore') -> Any:
    """Compact 6-panel header table showing live health of every pipeline component."""
    from rich.table import Table as _T
    ph = store.pipeline_health if hasattr(store, 'pipeline_health') else {}
    tt = store.trade_tracker

    # ── Color helpers ──
    def _ok(v):  return f"[bold green]{v}[/bold green]"
    def _warn(v): return f"[bold yellow]{v}[/bold yellow]"
    def _err(v): return f"[bold red]{v}[/bold red]"
    def _dim(v): return f"[dim]{v}[/dim]"
    def _status_color(status, ok_vals=("CONNECTED", "TESTNET", "LIVE", "NORMAL", "LOADED")):
        if status in ok_vals:
            return _ok(status)
        if status in ("INIT", "WARMING", "COOLDOWN"):
            return _warn(status)
        return _err(status)

    # ── Panel 1: Chrome CDP ──
    chrome_s = ph.get("chrome_status", "INIT")
    chrome_lat = ph.get("chrome_latency_ms", 0)
    chrome_polls = ph.get("chrome_polls", 0)
    p1 = (f"Status: {_status_color(chrome_s)}\n"
          f"Latency: {chrome_lat:.0f}ms\n"
          f"Polls: {chrome_polls:,}")

    # ── Panel 2: Binance Broker ──
    broker_s = ph.get("binance_broker_status", "INIT")
    broker_bal = ph.get("binance_broker_balance", 0)
    broker_pos = ph.get("binance_broker_positions", 0)
    p2 = (f"Status: {_status_color(broker_s, ('TESTNET', 'LIVE'))}\n"
          f"Balance: [cyan]${broker_bal:,.2f}[/cyan]\n"
          f"Positions: {broker_pos}")

    # ── Panel 3: Scraper Stream ──
    fps = ph.get("scraper_fps", 0)
    last_parse = ph.get("scraper_last_parse_ns", 0)
    parse_age = (time.time_ns() - last_parse) / 1e9 if last_parse else 999
    fps_str = _ok(f"{fps:.1f}") if fps > 0.5 else (_warn(f"{fps:.1f}") if fps > 0 else _err("0.0"))
    age_str = _ok(f"{parse_age:.0f}s") if parse_age < 30 else (_warn(f"{parse_age:.0f}s") if parse_age < 120 else _err(f"{parse_age:.0f}s"))
    ws_ticks = ph.get("binance_ws_ticks", 0)
    ws_s = ph.get("binance_ws_status", "INIT")
    p3 = (f"FPS: {fps_str} | Age: {age_str}\n"
          f"WS: {_status_color(ws_s)} | Ticks: {ws_ticks:,}")

    # ── Panel 4: Rolling Window Buffer ──
    pred = store.predictor
    if pred and hasattr(pred, 'candles_history'):
        buf_counts = []
        for sym in ALL_SYMBOLS[:14]:  # crypto symbols only
            n = len(pred.candles_history.get(sym, []))
            buf_counts.append(n)
        avg_buf = int(sum(buf_counts) / max(len(buf_counts), 1))
        min_buf = min(buf_counts) if buf_counts else 0
        warm_pct = min(100, int(avg_buf / 250 * 100))
        buf_color = _ok if warm_pct >= 100 else (_warn if warm_pct >= 50 else _err)
        p4 = (f"Avg: {buf_color(f'{avg_buf}/250')} ({warm_pct}%)\n"
              f"Min: {min_buf}/250")
    else:
        p4 = _dim("No predictor")

    # ── Panel 5: ML Predictor ──
    if pred and hasattr(pred, 'models'):
        total_models = sum(len(v) for v in pred.models.values())
        n_strats = sum(1 for v in pred.models.values() if v)
        ml_s = _ok(f"LOADED ({total_models})") if total_models >= 84 else (_warn(f"PARTIAL ({total_models})") if total_models > 0 else _err("UNLOADED"))
        p5 = (f"Models: {ml_s}\n"
              f"Strategies: {n_strats}/6 active")
    else:
        p5 = _dim("No predictor")

    # ── Panel 6: Risk Governor ──
    if tt:
        halt = getattr(tt, 'emergency_halt', False)
        capital = getattr(tt, 'current_capital', 0)
        daily_start = getattr(tt, 'daily_start_capital', capital)
        initial = getattr(tt, 'initial_capital', capital)
        equity = capital  # simplified — no unrealized PnL in header
        daily_dd = (daily_start - equity) / daily_start * 100 if daily_start > 0 else 0
        total_dd = (initial - equity) / initial * 100 if initial > 0 else 0

        if halt:
            gov_s = _err("EMERGENCY_HALT")
        elif daily_dd > 2.0 or total_dd > 4.0:
            gov_s = _warn("CAUTION")
        else:
            gov_s = _ok("NORMAL")

        # Check cooldowns
        now_t = time.time()
        cooldowns = getattr(tt, 'reentry_cooldown_until', {})
        active_cooldowns = sum(1 for v in cooldowns.values() if v > now_t)

        p6 = (f"Status: {gov_s}\n"
              f"Daily DD: {daily_dd:.1f}% | Total: {total_dd:.1f}%\n"
              f"Cooldowns: {active_cooldowns}")
    else:
        p6 = _dim("No tracker")

    # ── Build table ──
    tbl = _T(
        title="[bold bright_cyan]⚡ Pipeline Status[/bold bright_cyan]",
        header_style="bold bright_cyan",
        border_style="bright_blue",
        expand=True,
        show_lines=True,
    )
    tbl.add_column("Chrome CDP", justify="center", ratio=1)
    tbl.add_column("Binance Broker", justify="center", ratio=1)
    tbl.add_column("Data Stream", justify="center", ratio=1)
    tbl.add_column("Buffer", justify="center", ratio=1)
    tbl.add_column("ML Predictor", justify="center", ratio=1)
    tbl.add_column("Risk Governor", justify="center", ratio=1)
    tbl.add_row(p1, p2, p3, p4, p5, p6)
    return tbl


# --- DASHBOARD RENDERER ---
def render_table(snap: Dict[str, AssetSnapshot], trade_tracker: Any = None, store: Any = None) -> Any:
    t = Table(
        title="[bold bright_cyan]Coinglass + Binance Footprint Scraper Terminal[/bold bright_cyan]",
        header_style="bold bright_cyan",
        border_style="bright_blue",
        expand=True
    )
    cols = (
        "Symbol", "Price", "RSI", "FutCVD", "SpotCVD", "LiqL", "LiqS", "Fund", "LSR", "OI", 
        "CoinsB", "CoinsA", "USDB", "USDA", "Whale", "BuyC", "SellC", "FP_D", "FP_P", "ARM"
    )
    for col in cols:
        t.add_column(col, justify="center", no_wrap=True)
        
    now = time.time_ns()
    
    def fmt(v: float, fresh: bool, col_type: str = "generic") -> str:
        if v is None:
            return "[dim]--[/dim]"
        
        if col_type == "rsi":
            s = f"{v:.2f}"
        elif col_type == "fund":
            s = f"{v:+.6f}"
        elif col_type in ("cvd", "fp_d"):
            s = f"{v:+,.2f}"
            if abs(v) > 1e6:
                s = f"{v:+,.0f}"
        else:
            s = f"{v:,.2f}"
            if abs(v) > 1e6 and col_type not in ("price", "rsi", "fund", "lsr"):
                s = f"{v:,.0f}"
            
        if not fresh:
            return f"[dim red]{s}[/dim red]"
            
        if col_type == "price":
            return f"[bold yellow]{s}[/bold yellow]"
        elif col_type == "rsi":
            if v >= 70:
                return f"[bold red]{s}[/bold red]"
            elif v <= 30:
                return f"[bold green]{s}[/bold green]"
            return f"[cyan]{s}[/cyan]"
        elif col_type in ("cvd", "fp_d"):
            if v > 0:
                return f"[bold green]{s}[/bold green]"
            elif v < 0:
                return f"[bold red]{s}[/bold red]"
            return f"[dim]{s}[/dim]"
        elif col_type == "liq_long":
            return f"[bold bright_green]{s}[/bold bright_green]" if v > 0 else f"[dim]{s}[/dim]"
        elif col_type == "liq_short":
            return f"[bold bright_red]{s}[/bold bright_red]" if v < 0 else f"[dim]{s}[/dim]"
        elif col_type == "fund":
            if v > 0:
                return f"[bold green]{s}[/bold green]"
            elif v < 0:
                return f"[bold yellow]{s}[/bold yellow]"
            return f"[dim]{s}[/dim]"
        elif col_type == "lsr":
            return f"[bold cyan]{s}[/bold cyan]"
        elif col_type == "arm":
            if "LONG" in str(v):
                return f"[bold bright_green]{v}[/bold bright_green]"
            elif "SHORT" in str(v):
                return f"[bold bright_red]{v}[/bold bright_red]"
            elif "WARM" in str(v):
                return f"[bold yellow]{v}[/bold yellow]"
            elif "READY" in str(v):
                return f"[dim green]{v}[/dim green]"
            return f"[cyan]{v}[/cyan]"
        
        return f"[white]{s}[/white]"

    for sym in ALL_SYMBOLS:
        a = snap.get(sym, AssetSnapshot(symbol=sym))
        fresh = (now - a.ts_ns) < STALE_NS
        
        t.add_row(
            f"[bold bright_white]{sym}[/bold bright_white]",
            fmt(a.price, fresh, "price"),
            fmt(a.rsi, fresh, "rsi"),
            fmt(a.fut_cvd, fresh, "cvd"),
            fmt(a.spot_cvd, fresh, "cvd"),
            fmt(a.liq_long, fresh, "liq_long"),
            fmt(a.liq_short, fresh, "liq_short"),
            fmt(a.funding, fresh, "fund"),
            fmt(a.ls_ratio, fresh, "lsr"),
            fmt(a.oi, fresh, "generic"),
            fmt(a.coins_bid, fresh, "generic"),
            fmt(a.coins_ask, fresh, "generic"),
            fmt(a.dollars_bid, fresh, "generic"),
            fmt(a.dollars_ask, fresh, "generic"),
            fmt(a.whale_idx, fresh, "generic"),
            fmt(a.tk_buy_cnt, fresh, "generic"),
            fmt(a.tk_sell_cnt, fresh, "generic"),
            fmt(a.fp_delta, fresh, "fp_d"),
            fmt(a.fp_poc if a.fp_poc > 0 else a.price, fresh, "generic"),
            fmt(a.strategy_armed, fresh, "arm") if a.strategy_armed else "[dim]--[/dim]"
        )

    if trade_tracker is None:
        return t

    from rich.console import Group
    from rich.panel import Panel
    from rich.text import Text

    stats = trade_tracker.get_stats()
    
    # Active trades section
    active_lines = []
    with trade_tracker.lock:
        active_snap = list(trade_tracker.active_trades.values())
        history_snap = list(trade_tracker.history[-3:])

    for tr in active_snap:
        dir_str = "[bold bright_green]LONG[/bold bright_green]" if tr['direction'] == 1 else "[bold bright_red]SHORT[/bold bright_red]"
        pnl_usd = tr.get('live_pnl_usd', 0.0)
        pnl_pct = tr.get('live_pnl_pct', 0.0)
        pnl_str = f"[bold green]+${pnl_usd:.2f} (+{pnl_pct:+.2f}%)[/bold green]" if pnl_usd >= 0 else f"[bold red]-${abs(pnl_usd):.2f} ({pnl_pct:+.2f}%)[/bold red]"
        mt5_info = f" | MT5 Entry: {tr['mt5_entry']:.4f} (Lot: {tr['mt5_lot']:.2f})" if 'mt5_entry' in tr else ""
        active_lines.append(f"[bold bright_white]{tr['symbol']}[/] | {dir_str} | Entry: [cyan]{tr['entry_price']:.4f}[/] | SL: [red]{tr['sl']:.4f}[/] | TP: [green]{tr['tp']:.4f}[/] | Live PnL: {pnl_str}{mt5_info}")

    active_text = "\n".join(active_lines) if active_lines else "[dim]No active trades[/dim]"

    # History trades section (last 3)
    history_lines = []
    for tr in history_snap:
        dir_str = "[bold green]LONG[/]" if tr['direction'] == 1 else "[bold red]SHORT[/]"
        pnl_usd = tr.get('pnl_usd', 0.0)
        pnl_pct = tr.get('pnl_pct', 0.0)
        pnl_str = f"[bold green]+${pnl_usd:.2f} (+{pnl_pct:+.2f}%)[/]" if pnl_usd >= 0 else f"[bold red]-${abs(pnl_usd):.2f} ({pnl_pct:+.2f}%)[/]"
        reason = tr.get('exit_reason', 'EXIT')
        history_lines.append(f"{tr['symbol']} | {dir_str} | Exit: {tr['exit_price']:.4f} | Reason: {reason} | Final: {pnl_str}")

    history_text = "\n".join(history_lines) if history_lines else "[dim]No trade history[/dim]"

    # Stats string
    winrate = stats['winrate']
    total_pnl = stats['total_pnl_usd']
    pnl_pct = total_pnl / trade_tracker.initial_capital * 100.0 if trade_tracker.initial_capital > 0 else 0.0
    pnl_clr = "bright_green" if total_pnl >= 0 else "bright_red"
    pnl_sign = "+" if total_pnl >= 0 else ""

    stats_text = (
        f"Initial Capital: [bold bright_cyan]${trade_tracker.initial_capital:,.2f}[/]  |  Current Capital: [bold bright_cyan]${stats['current_capital']:.2f}[/]  |  "
        f"Total PnL: [bold {pnl_clr}]{pnl_sign}${total_pnl:.2f} ({pnl_pct:+.2f}%)[/]  |  "
        f"Trades: [bold bright_yellow]{stats['total']}[/]  |  Winrate: [bold bright_yellow]{winrate:.1f}%[/]"
    )

    trade_table = Table(show_header=True, header_style="bold bright_magenta", border_style="bright_magenta", expand=True)
    trade_table.add_column("Active Trades", justify="left", ratio=1)
    trade_table.add_column(stats_text, justify="left", ratio=1)
    trade_table.add_row(active_text, history_text)

    # Pipeline status header above main table
    if store and hasattr(store, 'pipeline_health'):
        pipeline_tbl = render_pipeline_status(store)
        return Group(pipeline_tbl, t, trade_table)
    return Group(t, trade_table)

async def renderer_loop(store: SnapshotStore, stop: asyncio.Event) -> None:
    console = Console()
    loop_cnt = 0
    init_table = await asyncio.to_thread(render_table, store.snapshot(), store.trade_tracker, store)
    with Live(init_table, console=console, refresh_per_second=REFRESH_HZ, screen=False) as live:
        while not stop.is_set():
            snap = store.snapshot()
            rendered = await asyncio.to_thread(render_table, snap, store.trade_tracker, store)
            live.update(rendered)
            
            loop_cnt += 1
            if loop_cnt % 20 == 0:  # Every 10 seconds at 2Hz REFRESH_HZ
                try:
                    serializable_snap = {}
                    for sym, a in snap.items():
                        serializable_snap[sym] = {
                            "price": a.price, "volume": a.volume, "rsi": a.rsi, "fut_cvd": a.fut_cvd, "spot_cvd": a.spot_cvd,
                            "liq_long": a.liq_long, "liq_short": a.liq_short, "funding": a.funding,
                            "ls_ratio": a.ls_ratio, "oi": a.oi,
                            "coins_bid": a.coins_bid, "coins_ask": a.coins_ask,
                            "dollars_bid": a.dollars_bid, "dollars_ask": a.dollars_ask,
                            "whale_idx": a.whale_idx, "tk_buy_cnt": a.tk_buy_cnt, "tk_sell_cnt": a.tk_sell_cnt,
                            "fp_delta": a.fp_delta, "fp_poc": a.fp_poc,
                            "strategy_armed": a.strategy_armed, "ts_ns": a.ts_ns
                        }
                    def _write_debug():
                        try:
                            tmp_path = os.path.join(base_dir, "Seeding", "snapshot_debug.json.tmp")
                            with open(tmp_path, "w", encoding="utf-8") as f:
                                json.dump(serializable_snap, f, indent=4)
                            os.replace(tmp_path, os.path.join(base_dir, "Seeding", "snapshot_debug.json"))
                        except Exception:
                            pass
                    await asyncio.to_thread(_write_debug)
                except Exception:
                    pass
            await asyncio.sleep(1.0 / REFRESH_HZ)

# --- WATCHDOG ---
async def watchdog(components: List[Any], focus_lock: asyncio.Lock, stop: asyncio.Event) -> None:
    # Initialize/reset heartbeats for all components on startup to ignore the configuration time
    now_start = time.time_ns()
    for c in components:
        if hasattr(c, 'last_heartbeat_ns'):
            c.last_heartbeat_ns = now_start

    tab_tasks = {}
    for c in components:
        if isinstance(c, CoinglassTab):
            tab_tasks[c] = asyncio.create_task(c.poll_loop())
            
    try:
        while not stop.is_set():
            now = time.time_ns()
            for c in components:
                if hasattr(c, 'last_heartbeat_ns') and now - c.last_heartbeat_ns > 90_000_000_000:
                    if getattr(c, 'skip_watchdog', False):
                        continue
                    print(f"[Watchdog] [WARN] Subsystem '{c.__class__.__name__}' ({getattr(c, 'tab_id', 'Unknown')}) hung. Heartbeat silent >90s.")
                    if isinstance(c, CoinglassTab):
                        print(f"[Watchdog] [RECOVERY] Attempting recovery for '{c.tab_id}'...")
                        if c in tab_tasks and not tab_tasks[c].done():
                            tab_tasks[c].cancel()
                            try:
                                await tab_tasks[c]
                            except asyncio.CancelledError:
                                pass
                        try:
                            await c.reconnect(focus_lock)
                            tab_tasks[c] = asyncio.create_task(c.poll_loop())
                            # Reset heartbeats for all components to prevent false positives from the blocking recovery
                            now_after = time.time_ns()
                            for comp in components:
                                if hasattr(comp, 'last_heartbeat_ns'):
                                    comp.last_heartbeat_ns = now_after
                        except Exception as rec_err:
                            print(f"[Watchdog] [ERROR] Recovery failed for '{c.tab_id}': {rec_err}")
            # Check Python process memory usage to catch memory leaks
            mem_mb = get_process_memory_usage() / (1024 * 1024)
            if mem_mb > 3584.0:  # 3.5 GB limit to allow initial retraining/seeding spikes
                print(f"\n[Watchdog] [ALERT] [MEMORY] Python memory usage is extremely high ({mem_mb:.1f} MB)!")
            await asyncio.sleep(5.0)
    finally:
        for task in tab_tasks.values():
            if not task.done():
                task.cancel()
        if tab_tasks:
            await asyncio.gather(*tab_tasks.values(), return_exceptions=True)

def combine_seeding_files() -> None:
    import glob
    import copy
    from openpyxl import load_workbook, Workbook
    from openpyxl.utils import get_column_letter

    files = glob.glob(os.path.join(base_dir, "Seeding", "*_seed_history.xlsx"))
    files = [f for f in files if "combined_seed" not in os.path.basename(f).lower()]
    if not files:
        print("[Setup] No seeding files found to combine.")
        return

    print(f"[Setup] Combining {len(files)} seeding files into a single workbook...")
    combined_wb = Workbook()
    default_sheet = combined_wb.active
    combined_wb.remove(default_sheet)

    for f in sorted(files):
        symbol = os.path.basename(f).replace("_seed_history.xlsx", "")
        try:
            wb = load_workbook(f)
            source_ws = wb.active
            target_ws = combined_wb.create_sheet(title=symbol[:31])

            for row in source_ws.iter_rows():
                for cell in row:
                    new_cell = target_ws.cell(row=cell.row, column=cell.column, value=cell.value)
                    if cell.has_style:
                        new_cell.font = copy.copy(cell.font)
                        new_cell.fill = copy.copy(cell.fill)
                        new_cell.border = copy.copy(cell.border)
                        new_cell.alignment = copy.copy(cell.alignment)
                        new_cell.number_format = cell.number_format

            for col in source_ws.columns:
                col_letter = get_column_letter(col[0].column)
                target_ws.column_dimensions[col_letter].width = source_ws.column_dimensions[col_letter].width
            wb.close()
        except Exception as copy_exc:
            print(f"[Setup] [WARN] Failed to copy {symbol} sheet: {copy_exc}")

    combined_filename = os.path.join(base_dir, "Seeding", "combined_seed_history.xlsx")
    tmp_filename = combined_filename + ".tmp"
    try:
        combined_wb.save(tmp_filename)
        os.replace(tmp_filename, combined_filename)
        print(f"[Setup] Combined workbook saved successfully: {combined_filename}")
        
        # Clean up individual seed files
        for f in files:
            try:
                os.remove(f)
            except OSError:
                pass
        print("[Setup] Cleaned up individual symbol seeding files.")
    except Exception as e:
        print(f"[Setup] [WARN] Failed to save combined workbook: {e}")

# --- MAIN CONTROLLER ---
async def main(skip_seed: bool = False, skip_train: bool = False) -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    binance_live = os.environ.get("BINANCE_LIVE", os.environ.get("MT5_LIVE", "0")) == "1"
    print("=" * 60)
    print(f"  SYSTEM STARTUP - MODE: {EXECUTION_MODE} (BINANCE FUTURES)")
    if binance_live:
        print("  TRADES ARE DISPATCHED TO BINANCE FUTURES DEMO ACCOUNT / LOCAL TRACKER")
    else:
        print("  WARNING: NO REAL BINANCE FUTURES TRADE ORDERS WILL BE SENT")
        print("  TRADES ARE SIMULATED LOCALLY IN THE TRACKER FILE")
    print("=" * 60)

    if skip_train:
        print("[Setup] Skipping initial ML model retraining (--skip-train passed). Using existing models.")
    else:
        # 0. Clear existing ML models to prevent conflicts before retraining
        print("[Setup] Clearing existing ML model files before retraining...")
        for sub in (ACTIVE_STRATEGY, 'Liquidation', 'ml_trend_pull', 'six_strategy_models'):
            m_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), sub, 'models') if sub != 'six_strategy_models' else os.path.join(os.path.dirname(os.path.abspath(__file__)), sub)
            if os.path.exists(m_dir):
                for file in os.listdir(m_dir):
                    if file.endswith(('.pkl', '.json', '.txt', '.cbm', '.pt')):
                        try:
                            os.remove(os.path.join(m_dir, file))
                        except Exception as clear_err:
                            print(f"[Setup] [WARN] Could not remove old model file {file}: {clear_err}")

        # 0. Live Model Retraining on latest Parquet data
        print(f"[Setup] Running Live Model Retraining on latest Parquet data...")
        
        # Train unified six-strategy models (84 files: 6 strategies × 14 symbols)
        try:
            import importlib
            base_dir = os.path.dirname(os.path.abspath(__file__))
            if base_dir not in sys.path:
                sys.path.insert(0, base_dir)
            sys.modules.pop('train_six_strategy', None)
            train_six_mod = importlib.import_module("train_six_strategy")
            print("[Setup] Training Six-Strategy ML models (S1-S6 × 14 symbols)...")
            train_six_mod.train_all_strategies()
            print("[Setup] ✓ Six-Strategy models trained successfully")
        except Exception as retrain_err:
            print(f"[Setup] [WARN] Failed to retrain Six-Strategy models: {retrain_err}")
            import traceback
            traceback.print_exc()

    # Initialize unified Six-Strategy Predictor (ports run_all_6.py verified strategies)
    predictor = LiveSixStrategyPredictor(ALL_SYMBOLS)
    
    # Load cached history from disk
    predictor.load_history_from_disk()
    print(f"[Setup] Six-Strategy Predictor initialized with {len(predictor.models)} model sets")

    trade_tracker = Engine1TradeTracker()
    def run_retrain_proc():
        import sys
        import os
        import importlib
        base_dir = os.path.dirname(os.path.abspath(__file__))
        if base_dir not in sys.path:
            sys.path.insert(0, base_dir)
            
        print(f"[Background Process] Starting Live Retraining for Six-Strategy models...")
        try:
            sys.modules.pop('train_six_strategy', None)
            train_six_mod = importlib.import_module("train_six_strategy")
            train_six_mod.train_all_strategies()
            print("[Background Process] ✓ Six-Strategy retraining completed")
        except Exception as e:
            print(f"[Background Process] Six-Strategy retrain failed: {e}")
            import traceback
            traceback.print_exc()
        print("[Background Process] Live Retraining finished.")

    def background_retrain_loop():
        import time
        import multiprocessing
        from datetime import datetime, timezone, timedelta

        # Target: 00:00 UTC (05:30 IST) — low-volatility off-peak window
        RETRAIN_HOUR_UTC = 0
        RETRAIN_MINUTE_UTC = 0

        while True:
            now_utc = datetime.now(timezone.utc)
            target = now_utc.replace(hour=RETRAIN_HOUR_UTC, minute=RETRAIN_MINUTE_UTC, second=0, microsecond=0)
            if target <= now_utc:
                target += timedelta(days=1)
            delay_secs = (target - now_utc).total_seconds()

            ist_offset = timedelta(hours=5, minutes=30)
            target_ist = target + ist_offset
            print(f"[Background Thread] Next retraining scheduled at {target.strftime('%Y-%m-%d %H:%M UTC')} ({target_ist.strftime('%H:%M IST')}) — in {delay_secs/3600:.1f} hours")
            time.sleep(delay_secs)

            print(f"[Background Thread] Launching scheduled Live Retraining Subprocess at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}...")
            try:
                p = multiprocessing.Process(target=run_retrain_proc)
                p.start()
                p.join()
            except Exception as ex:
                print(f"[Background Thread] Subprocess retraining manager crashed: {ex}")

    import threading
    retrain_thread = threading.Thread(target=background_retrain_loop, daemon=True)
    retrain_thread.start()
    print("[Setup] Launched 24hr Background Retraining Manager Thread (Process-isolated).")

    store = SnapshotStore(ALL_SYMBOLS, predictor, trade_tracker)

    # Initialize broker health status in pipeline
    if hasattr(trade_tracker, 'mt5_broker') and hasattr(trade_tracker.mt5_broker, 'broker'):
        raw_broker = trade_tracker.mt5_broker.broker
        is_testnet = getattr(raw_broker, 'use_testnet', False)
        is_dry = getattr(raw_broker, 'dry_run', True)
        store.pipeline_health["binance_broker_status"] = "TESTNET" if is_testnet else ("DRY_RUN" if is_dry else "LIVE")
        try:
            details = raw_broker.get_account_details()
            if details:
                store.pipeline_health["binance_broker_balance"] = details.get("balance", trade_tracker.initial_capital)
        except Exception:
            store.pipeline_health["binance_broker_balance"] = trade_tracker.initial_capital
    else:
        store.pipeline_health["binance_broker_status"] = "OFFLINE"
        store.pipeline_health["binance_broker_balance"] = trade_tracker.initial_capital
    stop = asyncio.Event()
    
    print("[Setup] Launching Chromium instance with persistent profile...")
    async with async_playwright() as pw:
        user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
        is_linux = sys.platform.startswith("linux")
        headless_flag = is_linux or os.environ.get("HEADLESS", "0") == "1"
        chrome_args = [
            "--disable-features=CalculateNativeWinOcclusion",
            "--disable-background-timer-throttling",
            "--start-maximized",
            "--remote-debugging-port=9222"
        ]
        if is_linux:
            chrome_args.extend([
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ])
        
        exec_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
        if not exec_path and is_linux:
            import shutil
            exec_path = shutil.which("chromium-browser") or shutil.which("chromium")

        launch_kwargs = {
            "headless": headless_flag,
            "viewport": {"width": 1920, "height": 1080},
            "args": chrome_args
        }
        if exec_path:
            launch_kwargs["executable_path"] = exec_path
        
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir,
            **launch_kwargs
        )
        
        # 1. Performing Session Login first
        print("[Setup] Navigating to Coinglass Login...")
        login_page = await ctx.new_page()
        
        for attempt in range(3):
            try:
                await login_page.goto("https://www.coinglass.com/login", wait_until="load", timeout=45000)
                break
            except Exception as exc:
                print(f"[Setup] [WARN] Login navigation attempt {attempt+1} failed: {exc}")
                if attempt == 2:
                    raise exc
                await asyncio.sleep(5.0)
        await asyncio.sleep(5)
        
        os.makedirs(os.path.join(base_dir, "Seeding"), exist_ok=True)
        await login_page.screenshot(path=os.path.join(base_dir, "Seeding", "login_init.png"))
        
        email_input = login_page.locator("input[placeholder='Email']").first
        if await email_input.count() > 0:
            email = os.environ.get("COINGLASS_EMAIL")
            password = os.environ.get("COINGLASS_PASSWORD")
            if not email or not password:
                print("[Setup] COINGLASS_EMAIL or COINGLASS_PASSWORD environment variables not set — skipping automated web login.")
            else:
                await email_input.click()
                await email_input.fill(email)
                await asyncio.sleep(0.3)

                pass_input = login_page.locator("input[placeholder='Password']").first
                await pass_input.click()
                await pass_input.fill(password)
                await asyncio.sleep(0.3)

                await login_page.screenshot(path=os.path.join(base_dir, "Seeding", "login_filled.png"))
                print("[Setup] Submitting login form...")

                # Try explicit button click first, fallback to JS click, last resort Enter key
                try:
                    btn = login_page.locator("button:has-text('Login')").first
                    if await btn.count() > 0:
                        await btn.wait_for(state="visible", timeout=5000)
                        await btn.click()
                    else:
                        raise Exception("button not found via locator")
                except Exception:
                    try:
                        await login_page.evaluate('''() => {
                            const b = Array.from(document.querySelectorAll('button'))
                                .find(el => el.textContent.trim() === 'Login');
                            if (b) b.click();
                        }''')
                    except Exception:
                        # Most reliable: press Enter on password field
                        await pass_input.press("Enter")

                print("[Setup] Waiting for post-login redirect...")
                try:
                    await login_page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
                    print("[Setup] Login successful — redirected away from /login.")
                except Exception:
                    print("[Setup] [WARN] No redirect detected — may already be logged in or login failed.")
                await login_page.screenshot(path=os.path.join(base_dir, "Seeding", "login_after_submit.png"))
                print("[Setup] Waiting 5 seconds to ensure session cookies are fully persisted...")
                await asyncio.sleep(5.0)
        else:
            print("[Setup] Form inputs not detected, assuming session already active.")
        
        # 2. Open Scraping Tabs (while login page is open to hold session cache)
        tab1 = CoinglassTab(ctx, TAB1_SYMBOLS, store, "TAB_1")
        tab2 = CoinglassTab(ctx, TAB2_SYMBOLS, store, "TAB_2")
        binance = BinanceFootprintFeed(ALL_SYMBOLS, store)
        binance_ws = BinanceTradePriceWebSocketFeed(ALL_SYMBOLS, store)
        
        await asyncio.gather(tab1.start(), tab2.start())
        
        # Close login page now that layout tabs have initialized
        try:
            await login_page.close()
        except Exception:
            pass
        
        # 3. Configure grid symbols & indicators
        focus_lock = asyncio.Lock()
        await asyncio.gather(
            tab1.inject_and_configure_all(focus_lock),
            tab2.inject_and_configure_all(focus_lock)
        )

        # 4. Historical Seeding
        from concurrent.futures import ThreadPoolExecutor
        excel_pool = ThreadPoolExecutor(max_workers=4)

        if skip_seed:
            print("[Setup] --skip-seed flag active. Skipping historical seeding.")
        else:
            async def seed_wrapper(tab: CoinglassTab, sym: str):
                try:
                    for attempt in range(3):
                        try:
                            if not tab.page or tab.page.is_closed():
                                print(f"[{tab.tab_id}] [RECOVERY] Page closed on seeding attempt {attempt+1}. Reconnecting...")
                                await tab.reconnect(focus_lock)
                            await tab.seed_symbol(sym, excel_pool, focus_lock)
                            break
                        except Exception as e:
                            print(f"[Setup] [WARN] Seeding failed for {sym} (attempt {attempt+1}/3): {e}")
                            if "closed" in str(e).lower() or "navigation" in str(e).lower() or "locator" in str(e).lower() or "timeout" in str(e).lower():
                                try:
                                    await tab.reconnect(focus_lock)
                                except Exception as rec_err:
                                    print(f"[Setup] [ERROR] Failed to reconnect tab during seeding retry: {rec_err}")
                            if attempt == 2:
                                raise
                            await asyncio.sleep(3.0)
                finally:
                    tab.is_seeding = False

            seeding_tasks = [seed_wrapper(tab1, sym) for sym in TAB1_SYMBOLS] + \
                            [seed_wrapper(tab2, sym) for sym in TAB2_SYMBOLS]

            print("[Setup] Launching historical seeding...")
            await asyncio.gather(*seeding_tasks)
            print("[Setup] Seeding phase complete! Starting real-time feeds...")
            combine_seeding_files()
        
        # 5. Run Live feeds & Terminal display
        async def tab_switcher():
            active_tab = tab1
            while not stop.is_set():
                await asyncio.sleep(60.0)
                if stop.is_set():
                    break
                if tab1.is_seeding or tab2.is_seeding:
                    continue
                try:
                    try:
                        async with asyncio.timeout(3.0):
                            async with focus_lock:
                                if active_tab.page and not active_tab.page.is_closed():
                                    await active_tab.page.bring_to_front()
                    except asyncio.TimeoutError:
                        print(f"[Switcher] Warning: focus_lock timeout. Bypassing lock to force {active_tab.name} to front.")
                        if active_tab.page and not active_tab.page.is_closed():
                            await active_tab.page.bring_to_front()
                            
                    active_tab = tab2 if active_tab is tab1 else tab1
                except Exception as e:
                    print(f"[Switcher] Failed to switch to {active_tab.name}: {e}")

        async def rollover_watchdog(tracker, stop_event):
            while not stop_event.is_set():
                try:
                    tracker.update_day()
                    # Non-blocking MT5 position sync (prevents order-tracking drift)
                    if hasattr(tracker, "reconcile_with_mt5"):
                        await asyncio.to_thread(tracker.reconcile_with_mt5)
                except Exception as ex:
                    print(f"[Watchdog] [ERROR] Rollover watchdog failed: {ex}")
                await asyncio.sleep(30.0)  # tighter sync cadence for exit safety

        async def event_loop_monitor(stop_event: asyncio.Event, threshold_sec: float = 2.0) -> None:
            consecutive_blocks = 0
            while not stop_event.is_set():
                start = time.time()
                await asyncio.sleep(0.1)
                elapsed = time.time() - start - 0.1
                if elapsed > threshold_sec:
                    consecutive_blocks += 1
                    if consecutive_blocks >= 10:
                        pass
                else:
                    consecutive_blocks = 0

        tasks = [
            asyncio.create_task(event_loop_monitor(stop)),
            asyncio.create_task(binance.run()),
            asyncio.create_task(binance_ws.run()),
            asyncio.create_task(renderer_loop(store, stop)),
            asyncio.create_task(watchdog([tab1, tab2, binance, binance_ws], focus_lock, stop)),
            asyncio.create_task(tab_switcher()),
            asyncio.create_task(rollover_watchdog(trade_tracker, stop))
        ]
        
        # Handle graceful exit triggers
        loop = asyncio.get_running_loop()
        def sig_handler():
            print("\n[Exit] Termination signal received. Stopping...")
            stop.set()
            tab1.running = False
            tab2.running = False
            binance.running = False
            
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, sig_handler)
            except NotImplementedError:
                pass
                
        try:
            while not stop.is_set():
                await asyncio.sleep(1.0)
        except (KeyboardInterrupt, SystemExit):
            sig_handler()
        finally:
            print("[Setup] Cleaning up tasks and closing browser...")
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            excel_pool.shutdown(wait=True)
            await ctx.close()
        
    print("[Exit] Shutdown complete.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Coinglass + Binance Footprint Scraper")
    parser.add_argument("--skip-seed", "--skip-seeding", action="store_true", help="Skip historical Excel seeding and go straight to live feeds")
    parser.add_argument("--skip-train", action="store_true", help="Skip initial model retraining at startup")
    args = parser.parse_args()
    asyncio.run(main(skip_seed=args.skip_seed, skip_train=args.skip_train))
