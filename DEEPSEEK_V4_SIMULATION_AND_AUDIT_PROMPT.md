# 🚀 DEEPSEEK-V4 ADVANCED QUANTITATIVE AUDIT & CONTEXT SIMULATION PROMPT

> **TARGET AGENT:** DeepSeek-V4 / Arena AI Elite Quantitative Systems Auditor  
> **MISSION:** Exhaustive Line-by-Line Context Simulation, Concurrency Audit & Subsystem Verification for `Engine_1` Real-Time Trading Pipeline.

---

## 1. EXECUTIVE SYSTEM ARCHITECTURE & QUANTITATIVE SPECIFICATION

`Engine_1` is an ultra-low-latency asynchronous Python 3.14 quantitative trading engine executing live order flow and statistical arbitrage across 18 institutional assets (14 Crypto Perpetuals + 4 Macro Commodities).

### 1.1 Dual Chrome Isolated Subprocess Topology
To circumvent Windows Chrome Singleton process aggregation, the pipeline spawns two strictly isolated Chrome processes with dedicated remote debugging ports and separate user data profiles:

| Window / Tab | Remote CDP Port | User Profile Directory | Assigned Asset Matrix (9 Cells per Tab) |
|---|---|---|---|
| **Tab 1** | `19899` | `chrome_profile_tab1` | `BTCUSDT`, `ETHUSDT`, `XRPUSDT`, `SOLUSDT`, `BNBUSDT`, `DOGEUSDT`, `ADAUSDT`, `TRXUSDT`, `LINKUSDT` |
| **Tab 2** | `19900` | `chrome_profile_tab2` | `AVAXUSDT`, `SUIUSDT`, `NEARUSDT`, `DOTUSDT`, `LTCUSDT`, `XAUUSDT`, `XAGUSDT`, `CLUSDT`, `NATGASUSDT` |

### 1.2 Core Architectural Invariants
1. **15-Minute Resolution Lock (`15m`):** Every single TradingView chart cell across all 18 iframes must be locked to the `15m` timeframe.
2. **Deterministic Login & Layout Sequence:**
   - Navigate to `https://www.coinglass.com/login`
   - Fill email (`singhkaranbir0248@gmail.com`) and password (`Lu$er2hero`)
   - Click the login button directly via `page.locator("button:has-text('Login'), button:has-text('Log In'), button[type='submit']").first`
   - Execute an explicit **5.0-second settlement pause** (`await asyncio.sleep(5.0)`) to allow session tokens (`CAUTH`, `cg_auth`, `csrf_token`) to persist
   - Open S9 multi-chart grid at `https://www.coinglass.com/tv/layout/s9` in a new page and close the login page
   - Trigger the `L_1` preset layout menu
   - Enforce 15m resolution across all 9 cells
   - Configure target symbol tickers into `#tv-ss` search inputs
3. **Machine Learning Predictor:** Evaluates 84 LightGBM and CatBoost models across 6 alpha strategies (`MOMENTUM_BREAKOUT`, `TREND_PULLBACK`, `MEAN_REVERSION`, `VOLATILITY_EXPANSION`, `LIQUIDITY_SWEEP`, `MICROSTRUCTURE_ORDERFLOW`), throttled to at most 1 evaluation per 2.0 seconds per asset.
4. **Risk Governor & Execution Safety:**
   - Zero-naked-window place-then-cancel `modify_sltp` order updates.
   - Athens server time (00:00 UTC / 05:30 IST) daily drawdown reset.
   - Hard daily loss threshold: -3.0% (-$3,000 on $100k equity).
   - Maximum gross notional cap: $100,000.

---

## 2. PRODUCTION IMPLEMENTATION CODE

```python
"""
Engine_1 Production Scraper, SnapshotStore & Playwright Automated Setup Blueprint
"""

import os
import re
import sys
import time
import socket
import asyncio
import logging
import dataclasses
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, BrowserContext, Page

EMAIL_VAL = "singhkaranbir0248@gmail.com"
PASS_VAL = "Lu$er2hero"

TAB1_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT"]
TAB2_SYMBOLS = ["AVAXUSDT", "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT", "XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"]
ALL_SYMBOLS = TAB1_SYMBOLS + TAB2_SYMBOLS

@dataclasses.dataclass
class AssetSnapshot:
    symbol: str
    price: float = 0.0
    volume: float = 0.0
    rsi: float = 50.0
    fut_cvd: float = 0.0
    spot_cvd: float = 0.0
    funding: float = 0.0
    oi: float = 0.0
    liq_long: float = 0.0
    liq_short: float = 0.0
    fp_delta: float = 0.0
    fp_poc: float = 0.0
    ema_8: float = 0.0
    ema_21: float = 0.0
    ema_50: float = 0.0
    ema_200: float = 0.0
    ema_800: float = 0.0
    atr_14: float = 0.0
    atr_100: float = 0.0

class SnapshotStore:
    def __init__(self, symbols: List[str], predictor=None, trade_tracker=None):
        self._data: Dict[str, AssetSnapshot] = {s: AssetSnapshot(symbol=s) for s in symbols}
        self._locks = {s: asyncio.Lock() for s in symbols}
        self.predictor = predictor
        self.trade_tracker = trade_tracker
        self._last_ml_dispatch_ts: Dict[str, float] = {}

    async def update(self, symbol: str, updates: dict, trigger_ml: bool = True):
        async with self._locks[symbol]:
            cur = self._data[symbol]
            new_fields = {k: v for k, v in updates.items() if hasattr(cur, k) and v is not None}
            self._data[symbol] = dataclasses.replace(cur, **new_fields)
            
            if trigger_ml and self.predictor:
                now_t = time.time()
                last_t = self._last_ml_dispatch_ts.get(symbol, 0.0)
                if now_t - last_t >= 2.0:
                    self._last_ml_dispatch_ts[symbol] = now_t
                    if hasattr(self.predictor, "on_tick_update"):
                        self.predictor.on_tick_update(symbol, self._data[symbol])

async def run_coinglass_login_and_setup(context: BrowserContext, symbols: list[str], tab_label: str) -> Page:
    page = await context.new_page()
    await page.goto("https://www.coinglass.com/login", wait_until="domcontentloaded", timeout=45000)
    await asyncio.sleep(2.0)
    
    # 1. Fill credentials
    email_box = page.locator("input[type='email'], input[name='email'], input[placeholder*='Email'], input[type='text']").first
    await email_box.click()
    await email_box.fill(EMAIL_VAL)
    
    pass_box = page.locator("input[type='password']").first
    await pass_box.click()
    await pass_box.fill(PASS_VAL)
    
    # 2. Click Login button & wait 5.0 seconds
    login_btn = page.locator("button:has-text('Login'), button:has-text('Log In'), button[type='submit']").first
    if await login_btn.is_visible(timeout=3000):
        await login_btn.click()
    else:
        await pass_box.press("Enter")
        
    await asyncio.sleep(5.0)  # Session settlement
    
    # 3. Mount S9 Layout & Close Login Page
    page1 = await context.new_page()
    await page1.goto("https://www.coinglass.com/tv/layout/s9", wait_until="domcontentloaded", timeout=60000)
    await page.close()
    await asyncio.sleep(5.0)
    
    # 4. Load Custom Layout L_1
    try:
        await page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3).click(timeout=5000)
        await asyncio.sleep(1.0)
        await page1.get_by_role("menuitem", name="Load Chart Layout").click(timeout=5000)
        await asyncio.sleep(1.0)
        await page1.get_by_role("button", name="L_1").click(timeout=5000)
        await asyncio.sleep(4.0)
    except Exception:
        pass
    await page1.keyboard.press("Escape")
    
    # 5. Lock 15m Timeframe & Configure 9 Symbols
    grid_frames = [f for f in page1.frames if "tradingview" in f.name.lower() or "chart" in f.url.lower()]
    for idx in range(min(9, len(grid_frames))):
        frame = grid_frames[idx]
        try:
            canvas = frame.locator("canvas").nth(1)
            if await canvas.is_visible(timeout=2000):
                await canvas.click(position={"x": 288, "y": 89})
            await page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(2).click()
            await page1.locator(".MuiMenuItem-root, div, button").filter(has_text=re.compile(r"^15m$")).first.click()
            await page1.keyboard.press("Escape")
        except Exception:
            await page1.keyboard.press("Escape")
            
    for idx, sym in enumerate(symbols[:len(grid_frames)]):
        frame = grid_frames[idx]
        try:
            canvas = frame.locator("canvas").nth(1)
            if await canvas.is_visible(timeout=2000):
                await canvas.click(position={"x": 327, "y": 101})
            await page1.get_by_role("button").first.click()
            ss_input = page1.locator("#tv-ss")
            await ss_input.fill(sym)
            await asyncio.sleep(0.5)
            item = page1.locator(".symbol-item, [class*='search-item'], button").filter(has_text=sym).first
            if await item.is_visible(timeout=2000):
                await item.click()
            else:
                await ss_input.press("Enter")
        except Exception:
            await page1.keyboard.press("Escape")
            
    return page1
```

---

## 3. AUDIT & SIMULATION DIRECTIVES FOR DEEPSEEK-V4

As the auditing intelligence, execute a complete line-by-line simulation and state analysis addressing:

1. **DOM Locator & Action Simulation:**
   - Trace the exact locator resolution for `button:has-text('Login')` versus `get_by_role("button", name="Login").nth(1)` and explain why `.first` on text match succeeds on Material-UI buttons with blank sibling icons.
   - Evaluate the impact of the 5.0-second settlement wait on Playwright cookie synchronization.

2. **Concurrency & Thread Safety Audit:**
   - Audit the per-symbol `asyncio.Lock` mechanism in `SnapshotStore.update()`.
   - Verify whether concurrent updates from Binance WebSocket and CoinGlass DOM scrapers can cause lock starvation or race conditions in the 2 Hz ANSI terminal renderer.

3. **Risk Governor Mathematical Verification:**
   - Analyze the `modify_sltp` place-then-cancel invariant to verify whether a failure in the Binance API could ever leave a position unhedged (naked window).
   - Verify the Athens daily drawdown rollover equation at 00:00 UTC.

4. **10-Gate Audit Report:**
   - Produce a structured markdown table rating each of the 10 subsystems (PASS/FAIL) with mathematical justification.
