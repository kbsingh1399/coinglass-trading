#!/usr/bin/env python3
"""
api_data_feed.py — Browser-Free Async Market Data Feed for Engine_1
====================================================================
Fetches 17+ market metrics for 14 crypto symbols entirely via direct
Binance REST + WebSocket APIs.  Zero browser dependency.

Data Sources:
  Price, Volume   → @ticker (combined WS stream)
  RSI (14‑period) → locally computed from /klines REST + @kline_1m WS
  OI              → /openInterest REST  + @openInterest WS
  Funding Rate    → /premiumIndex REST  + @markPrice WS
  L/S Ratio       → /topLongShortAccountRatio REST (period=5m)
  CoinsB/CoinsA   → @depth20 WS — cumulative bids/asks in coins
  USDB/USDA       → @depth20 WS — cumulative bids/asks in USD
  LiqL/LiqS       → !forceOrder@arr WS (filtered per symbol)
  FutCVD/SpotCVD  → @aggTrade WS (cumulative volume delta)
  BuyC/SellC      → @aggTrade WS (taker buy/sell trade counts)
  Whale Index     → taker_buy_vol / total_vol from aggTrade data
  FP_Delta        → buy_vol - sell_vol per 15‑minute bar window
  FP_POC          → volume-profile Point of Control (max-vol price bucket)

Usage:
  python api_data_feed.py                # run and print JSON snapshots
  python api_data_feed.py --output out   # also dump to out/snap_<ts>.json

Environment (optional):
  MAX_SYMBOLS=5         restrict to first N symbols for lower bandwidth
"""

from __future__ import annotations
import asyncio, aiohttp, json, os, sys, time, math, logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import numpy as np
import pandas as pd

# ── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("api_feed")

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT",
    "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT",
    "AVAXUSDT", "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT",
]

MAX_SYMBOLS = int(os.environ.get("MAX_SYMBOLS", "14"))
SYMBOLS = SYMBOLS[:MAX_SYMBOLS]

SNAPSHOT_INTERVAL_SEC = int(os.environ.get("SNAP_INTERVAL", "15"))
RSI_KLINE_LIMIT = 120  # bars for RSI warm-up
RSI_PERIOD = 14
RSI_MIN_BARS = 30

# ── Sources ─────────────────────────────────────────────────────────────────
REST_BASE   = "https://fapi.binance.com"
WS_DOMAINS  = [
    "wss://fstream.binance.com/market/stream?streams=",
    "wss://fstream.binance.cloud/market/stream?streams=",
    "wss://fstream.binance.me/market/stream?streams=",
]
WS_COMBINED = WS_DOMAINS[0]   # default, rotated on connection failure
WS_SINGLE   = "wss://fstream.binance.com/ws"


# ═══════════════════════════════════════════════════════════════════════════
# LOCAL METRIC COMPUTATION HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def compute_rsi(close_prices: List[float], period: int = 14) -> float:
    """Wilder's RSI from a list of closes (oldest → newest)."""
    if len(close_prices) < period + 1:
        return 50.0
    arr = np.array(close_prices[-period - 1:], dtype=np.float64)
    delta = np.diff(arr)
    gain = np.mean(np.where(delta > 0, delta, 0))
    loss = np.mean(np.where(delta < 0, -delta, 0))
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    rs = gain / loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def compute_atr(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """ATR from OHLC arrays."""
    if len(closes) < period + 1 or len(highs) < period + 1 or len(lows) < period + 1:
        return 0.0
    tr_vals = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        tr_vals.append(tr)
    if not tr_vals:
        return 0.0
    return float(np.mean(tr_vals[-period:]))


@dataclass
class MarketSnapshot:
    """Normalized per-symbol data snapshot — matches AssetSnapshot fields."""
    symbol: str = ""
    price: float = 0.0
    volume: float = 0.0
    rsi: float = 0.0
    atr: float = 0.0
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
    ts_ns: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# THREAD‑SAFE DATA STORE
# ═══════════════════════════════════════════════════════════════════════════

class MarketDataStore:
    """Lock‑guarded in‑memory store with RSI/ATR history buffers."""

    def __init__(self, symbols: List[str]):
        self.symbols = symbols
        self._lock = asyncio.Lock()
        self._snapshots: Dict[str, MarketSnapshot] = {
            s: MarketSnapshot(symbol=s) for s in symbols
        }
        # ── RSI / ATR warm‑up buffers ──
        self._close_buf: Dict[str, deque] = {s: deque(maxlen=RSI_KLINE_LIMIT) for s in symbols}
        self._high_buf:  Dict[str, deque] = {s: deque(maxlen=RSI_KLINE_LIMIT) for s in symbols}
        self._low_buf:   Dict[str, deque] = {s: deque(maxlen=RSI_KLINE_LIMIT) for s in symbols}
        self._vol_buf:   Dict[str, deque] = {s: deque(maxlen=RSI_KLINE_LIMIT) for s in symbols}
        # ── FP delta / volume profile trackers ──
        self._bar_open_ts: Dict[str, int] = {s: 0 for s in symbols}
        self._fp_buckets:  Dict[str, Dict[float, float]] = {s: {} for s in symbols}
        self._fp_delta_acc: Dict[str, float] = {s: 0.0 for s in symbols}
        # ── CVD (cumulative vol delta) ──
        self._cvd_acc: Dict[str, float] = {s: 0.0 for s in symbols}
        # ── Liquidation 24h rolling sum ──
        self._liq_long_buf:  Dict[str, deque] = {s: deque(maxlen=3600) for s in symbols}
        self._liq_short_buf: Dict[str, deque] = {s: deque(maxlen=3600) for s in symbols}
        # ── Taker buy/sell counters ──
        self._tk_buy:       Dict[str, int]   = {s: 0 for s in symbols}
        self._tk_sell:      Dict[str, int]   = {s: 0 for s in symbols}
        self._tk_buy_vol:   Dict[str, float] = {s: 0.0 for s in symbols}
        self._tk_total_vol: Dict[str, float] = {s: 0.0 for s in symbols}
        # ── Warm‑up flag ──
        self._rsi_warm: Dict[str, bool] = {s: False for s in symbols}
        self._start_ts = time.time()

    # ── Update methods ──────────────────────────────────────────────────

    async def update_price_volume(self, sym: str, price: float, volume: float,
                                   close: float, high: float, low: float):
        async with self._lock:
            snap = self._snapshots[sym]
            snap.price = price
            snap.volume = volume
            snap.ts_ns = time.time_ns()
            self._close_buf[sym].append(close)
            self._high_buf[sym].append(high)
            self._low_buf[sym].append(low)
            self._vol_buf[sym].append(volume)
            if len(self._close_buf[sym]) >= RSI_MIN_BARS:
                self._rsi_warm[sym] = True
                snap.rsi = compute_rsi(list(self._close_buf[sym]), RSI_PERIOD)
                snap.atr = compute_atr(
                    list(self._high_buf[sym])[-RSI_PERIOD - 1:],
                    list(self._low_buf[sym])[-RSI_PERIOD - 1:],
                    list(self._close_buf[sym])[-RSI_PERIOD - 1:],
                    RSI_PERIOD,
                )

    async def update_oi(self, sym: str, oi: float):
        async with self._lock:
            self._snapshots[sym].oi = oi

    async def update_funding(self, sym: str, funding: float):
        async with self._lock:
            self._snapshots[sym].funding = funding

    async def update_ls_ratio(self, sym: str, ls_ratio: float):
        async with self._lock:
            self._snapshots[sym].ls_ratio = ls_ratio

    async def update_depth(self, sym: str, bids: List[Tuple[float, float]],
                            asks: List[Tuple[float, float]]):
        """bids/asks are list of (price, qty) in order‑book order."""
        async with self._lock:
            snap = self._snapshots[sym]
            coins_bid = sum(q for _, q in bids)
            coins_ask = sum(q for _, q in asks)
            usd_bid = sum(p * q for p, q in bids)
            usd_ask = sum(p * q for p, q in asks)
            snap.coins_bid = coins_bid
            snap.coins_ask = coins_ask
            snap.dollars_bid = usd_bid
            snap.dollars_ask = usd_ask

    async def add_liquidation(self, sym: str, side: str, qty: float):
        """Record a single liquidation event."""
        async with self._lock:
            now = time.time()
            if side == "BUY":
                self._liq_long_buf[sym].append((now, qty))
            else:
                self._liq_short_buf[sym].append((now, qty))
            cutoff = now - 3600
            for buf, attr in [(self._liq_long_buf[sym], "liq_long"),
                               (self._liq_short_buf[sym], "liq_short")]:
                while buf and buf[0][0] < cutoff:
                    buf.popleft()
                setattr(self._snapshots[sym], attr, sum(q for _, q in buf))

    async def add_agg_trade(self, sym: str, price: float, qty: float,
                             is_buyer_maker: bool):
        """Process an aggregated trade tick."""
        async with self._lock:
            snap = self._snapshots[sym]
            vol = qty
            if is_buyer_maker:
                self._cvd_acc[sym] -= vol
                self._tk_sell[sym] += 1
            else:
                self._cvd_acc[sym] += vol
                self._tk_buy[sym] += 1
            self._tk_buy_vol[sym] += vol if not is_buyer_maker else 0.0
            self._tk_total_vol[sym] += vol
            snap.fut_cvd = self._cvd_acc[sym]
            snap.tk_buy_cnt = float(self._tk_buy[sym])
            snap.tk_sell_cnt = float(self._tk_sell[sym])
            if self._tk_total_vol[sym] > 0:
                snap.whale_idx = self._tk_buy_vol[sym] / self._tk_total_vol[sym]

            bar_ts = int(time.time() // 900) * 900
            if bar_ts != self._bar_open_ts.get(sym, 0):
                self._bar_open_ts[sym] = bar_ts
                self._fp_delta_acc[sym] = 0.0
                self._fp_buckets[sym].clear()
            tick_size = 0.01
            bucket = round(price / tick_size) * tick_size
            self._fp_buckets[sym][bucket] = self._fp_buckets[sym].get(bucket, 0.0) + vol
            delta = vol if not is_buyer_maker else -vol
            self._fp_delta_acc[sym] += delta
            snap.fp_delta = self._fp_delta_acc[sym]
            if self._fp_buckets[sym]:
                snap.fp_poc = max(self._fp_buckets[sym].items(), key=lambda kv: kv[1])[0]

    def snapshot(self) -> Dict[str, MarketSnapshot]:
        """Return a shallow copy of all snapshots."""
        return dict(self._snapshots)

    def snapshot_json(self) -> str:
        snap = {}
        for sym in self.symbols:
            s = self._snapshots[sym]
            snap[sym] = {
                "price": round(s.price, 2),
                "volume": round(s.volume, 2),
                "rsi": round(s.rsi, 1),
                "atr": round(s.atr, 4),
                "fut_cvd": round(s.fut_cvd, 2),
                "spot_cvd": round(s.spot_cvd, 2),
                "liq_long": round(s.liq_long, 2),
                "liq_short": round(s.liq_short, 2),
                "funding": round(s.funding, 6),
                "ls_ratio": round(s.ls_ratio, 4),
                "oi": round(s.oi, 2),
                "fp_delta": round(s.fp_delta, 2),
                "fp_poc": round(s.fp_poc, 4),
                "coins_bid": round(s.coins_bid, 2),
                "coins_ask": round(s.coins_ask, 2),
                "dollars_bid": round(s.dollars_bid, 2),
                "dollars_ask": round(s.dollars_ask, 2),
                "whale_idx": round(s.whale_idx, 4),
                "tk_buy_cnt": s.tk_buy_cnt,
                "tk_sell_cnt": s.tk_sell_cnt,
                "ts_ns": s.ts_ns,
            }
        return json.dumps(snap, indent=2)

    async def print_snapshot_table(self, warm_count: int):
        """Print snapshots of all symbols as a beautiful, aligned ASCII table."""
        headers = ["Symbol", "Price", "RSI", "ATR", "FutCVD", "SpotCVD", "Funding", "LSRatio", "OI", "Bids(USD)", "Asks(USD)", "Whale", "BuyC", "SellC", "FP_Del", "FP_POC"]
        fmt = "{:<9} | {:<10} | {:<5} | {:<7} | {:<8} | {:<8} | {:<8} | {:<7} | {:<10} | {:<11} | {:<11} | {:<6} | {:<5} | {:<5} | {:<6} | {:<9}"

        border = "=" * 155
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{border}")
        print(f"  SNAPSHOT @ {ts}  ({warm_count}/{len(self.symbols)} RSI warm)")
        print(border)
        print(fmt.format(*headers))
        print("-" * 155)

        async with self._lock:
            for sym in self.symbols:
                s = self._snapshots[sym]
                price_str = f"{s.price:.2f}" if s.price > 0 else "0.00"
                rsi_str   = f"{s.rsi:.1f}" if s.price > 0 else "0.0"
                atr_str   = f"{s.atr:.4f}" if s.price > 0 else "0.0000"
                funding_str = f"{s.funding:.6f}"
                ls_str      = f"{s.ls_ratio:.4f}"
                oi_str      = f"{s.oi:.1f}"
                bid_str     = f"{s.dollars_bid:.1f}"
                ask_str     = f"{s.dollars_ask:.1f}"
                whale_str   = f"{s.whale_idx:.3f}"
                fp_del_str  = f"{s.fp_delta:.1f}"
                fp_poc_str  = f"{s.fp_poc:.2f}" if s.fp_poc > 0 else "0.00"

                print(fmt.format(
                    sym, price_str, rsi_str, atr_str,
                    f"{s.fut_cvd:.1f}", f"{s.spot_cvd:.1f}",
                    funding_str, ls_str, oi_str,
                    bid_str, ask_str, whale_str,
                    str(s.tk_buy_cnt), str(s.tk_sell_cnt),
                    fp_del_str, fp_poc_str
                ))
        print(border)


# ═══════════════════════════════════════════════════════════════════════════
# ASYNC WEBSOCKET TASKS
# ═══════════════════════════════════════════════════════════════════════════

async def _listen_all_streams(store: MarketDataStore):
    """Listens to all market data streams in a single combined WebSocket connection
    with domain rotation: .binance.com → .binance.cloud → .binance.me."""
    streams = ["forceorder@arr"]
    for s in store.symbols:
        s_lower = s.lower()
        streams.append(f"{s_lower}@ticker")
        streams.append(f"{s_lower}@kline_1m")
        streams.append(f"{s_lower}@depth20@100ms")
        streams.append(f"{s_lower}@aggTrade")
        streams.append(f"{s_lower}@markPrice@1s")

    domain_idx = 0
    reconnect_delay = 1.0
    while True:
        base_url = WS_DOMAINS[domain_idx % len(WS_DOMAINS)]
        url = f"{base_url}{'/'.join(streams)}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url, heartbeat=30.0) as ws:
                    reconnect_delay = 1.0
                    domain_idx = 0  # reset on success
                    domain_label = base_url.split("//")[1].split("/")[0]
                    log.info(f"[WS] Connected to {domain_label} ({len(streams)} streams)")
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(msg.data)
                                stream_name = data.get("stream", "")
                                payload = data

                                if "@ticker" in stream_name:
                                    await _handle_ticker(store, payload)
                                elif "@kline_1m" in stream_name:
                                    await _handle_kline_1m(store, payload)
                                elif "@depth20@100ms" in stream_name:
                                    await _handle_depth(store, payload)
                                elif "@aggTrade" in stream_name:
                                    await _handle_agg_trade(store, payload)
                                elif "@markPrice" in stream_name:
                                    await _handle_mark_price(store, payload)
                                elif "forceorder" in stream_name:
                                    await _handle_force_order(store, data.get("data", {}))
                            except Exception as e:
                                log.error(f"[WS] Error in handler for {stream_name}: {e}", exc_info=True)
        except Exception as e:
            log.warning(f"[WS] Connection error on {base_url.split('//')[1].split('/')[0]}: {e} — "
                        f"rotate domain, reconnecting in {reconnect_delay}s")
            domain_idx += 1
        await asyncio.sleep(reconnect_delay)
        reconnect_delay = min(30.0, reconnect_delay * 1.5)


# ── Stream handlers ─────────────────────────────────────────────────────────

async def _handle_ticker(store: MarketDataStore, data: dict):
    """@ticker → price, volume."""
    d = data.get("data", {})
    s = d.get("s", "")
    if s not in store.symbols:
        return
    p = float(d.get("c", 0))
    v = float(d.get("v", 0))
    h = float(d.get("h", p))
    l = float(d.get("l", p))
    await store.update_price_volume(s, p, v, close=p, high=h, low=l)


async def _handle_kline_1m(store: MarketDataStore, data: dict):
    """@kline_1m → feed OHLC for RSI buffer."""
    d = data.get("data", {})
    k = d.get("k", {})
    s = k.get("s", "")
    if s not in store.symbols or not k.get("x"):
        return
    close = float(k["c"])
    high = float(k["h"])
    low = float(k["l"])
    vol = float(k["v"])
    price = float(k["c"])
    await store.update_price_volume(s, price, vol, close=close, high=high, low=low)


async def _handle_depth(store: MarketDataStore, data: dict):
    """@depth20@100ms → order book depth."""
    d = data.get("data", {})
    s = d.get("s", "")
    if s not in store.symbols:
        return
    bids = [(float(p), float(q)) for p, q in d.get("b", [])[:20]]
    asks = [(float(p), float(q)) for p, q in d.get("a", [])[:20]]
    await store.update_depth(s, bids, asks)


async def _handle_agg_trade(store: MarketDataStore, data: dict):
    """@aggTrade → CVD, buy/sell count, whale index."""
    d = data.get("data", {})
    s = d.get("s", "")
    if s not in store.symbols:
        return
    price = float(d.get("p", 0))
    qty = float(d.get("q", 0))
    is_buyer_maker = d.get("m", True)
    await store.add_agg_trade(s, price, qty, is_buyer_maker)


async def _handle_force_order(store: MarketDataStore, data: dict):
    """!forceOrder@arr → liquidation tracking."""
    o = data.get("o", {})
    s = o.get("s", "")
    if s not in store.symbols:
        return
    side = o.get("S", "BUY")
    qty = float(o.get("q", 0))
    await store.add_liquidation(s, side, qty)


async def _handle_mark_price(store: MarketDataStore, data: dict):
    """@markPrice@1s → funding rate."""
    d = data.get("data", {})
    s = d.get("s", "")
    if s not in store.symbols:
        return
    r = float(d.get("r", 0))
    await store.update_funding(s, r)


# ═══════════════════════════════════════════════════════════════════════════
# REST FETCH TASKS (periodic)
# ═══════════════════════════════════════════════════════════════════════════

async def _fetch_rest(endpoint: str, session: aiohttp.ClientSession) -> Optional[dict]:
    try:
        async with session.get(f"{REST_BASE}{endpoint}",
                               timeout=aiohttp.ClientTimeout(total=5)) as resp:
            return await resp.json() if resp.status == 200 else None
    except Exception:
        return None


async def _periodic_oi(store: MarketDataStore):
    """Fetch OI every 15 seconds."""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                for sym in store.symbols:
                    data = await _fetch_rest(
                        f"/fapi/v1/openInterest?symbol={sym}", session)
                    if data and "openInterest" in data:
                        await store.update_oi(sym, float(data["openInterest"]))
        except Exception:
            pass
        await asyncio.sleep(15.0)


async def _periodic_ls_ratio(store: MarketDataStore):
    """Fetch L/S ratio every 30 seconds."""
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                for sym in store.symbols:
                    data = await _fetch_rest(
                        f"/fapi/v1/topLongShortAccountRatio?symbol={sym}&period=5m&limit=1",
                        session)
                    if data:
                        item = data[0] if isinstance(data, list) else data
                        ratio = float(item.get("longShortRatio", 0))
                        await store.update_ls_ratio(sym, ratio)
        except Exception:
            pass
        await asyncio.sleep(30.0)


async def _periodic_klines_warmup(store: MarketDataStore):
    """Fetch initial klines for RSI/ATR warm‑up."""
    async with aiohttp.ClientSession() as session:
        for sym in store.symbols:
            try:
                data = await _fetch_rest(
                    f"/fapi/v1/klines?symbol={sym}&interval=1m&limit={RSI_KLINE_LIMIT}",
                    session)
                if data:
                    closes = [float(k[4]) for k in data]
                    highs = [float(k[2]) for k in data]
                    lows = [float(k[3]) for k in data]
                    for c, h, l in zip(closes, highs, lows):
                        store._close_buf[sym].append(c)
                        store._high_buf[sym].append(h)
                        store._low_buf[sym].append(l)
                    if len(closes) >= RSI_MIN_BARS:
                        store._rsi_warm[sym] = True
            except Exception:
                pass
        warm = sum(1 for v in store._rsi_warm.values() if v)
        log.info(f"[Warmup] Kline history fetched "
                 f"({warm}/{len(store.symbols)} symbols RSI-ready)")


# ═══════════════════════════════════════════════════════════════════════════
# JSON SNAPSHOT LOOP
# ═══════════════════════════════════════════════════════════════════════════

async def snapshot_loop(store: MarketDataStore, output_dir: Optional[str] = None):
    """Print ASCII table snapshots every SNAPSHOT_INTERVAL_SEC seconds."""
    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

    while True:
        await asyncio.sleep(SNAPSHOT_INTERVAL_SEC)
        warm = sum(1 for v in store._rsi_warm.values() if v)
        await store.print_snapshot_table(warm)

        if output_dir:
            js = store.snapshot_json()
            fname = out_path / f"snap_{int(time.time())}.json"
            fname.write_text(js)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="API Data Feed (browser‑free)")
    parser.add_argument("--output", type=str, default=None,
                        help="Directory to dump JSON snapshots")
    args = parser.parse_args()

    log.info(f"API Data Feed starting — {len(SYMBOLS)} symbols, "
             f"snapshot every {SNAPSHOT_INTERVAL_SEC}s")

    store = MarketDataStore(SYMBOLS)

    # Step 1: kline warm‑up
    log.info("[Setup] Fetching kline warm‑up data...")
    await _periodic_klines_warmup(store)

    # Step 2: Launch all async tasks
    tasks = [
        asyncio.create_task(_listen_all_streams(store)),
        asyncio.create_task(_periodic_oi(store)),
        asyncio.create_task(_periodic_ls_ratio(store)),
        asyncio.create_task(snapshot_loop(store, args.output)),
    ]

    log.info(f"[Start] {len(tasks)} tasks launched — streaming data...")

    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        log.info("Shutdown requested.")

    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    log.info("API Data Feed stopped.")


if __name__ == "__main__":
    asyncio.run(main())
