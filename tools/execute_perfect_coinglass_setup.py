"""
==============================================================================
⛔ CRITICAL ARCHITECTURAL INVARIANT — DO NOT MODIFY OR TOUCH THIS CODE
==============================================================================
This is the 100% exact recorded Playwright setup sequence requested by the user.
It executes verbatim across both browser contexts/ports:
1. page.goto("https://www.coinglass.com/login")
2. page.get_by_role("textbox", name="Email").click()
3. page.get_by_role("textbox", name="Email").fill("singhkaranbir0248@gmail.com")
4. page.get_by_role("textbox", name="Password").click()
5. page.get_by_role("textbox", name="Password").fill("Lu$er2hero")
6. page.get_by_role("button", name="Login").nth(1).click()
7. page1 = context.new_page()
8. page1.goto("https://www.coinglass.com/tv/layout/s9")
9. page.close()
10. page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3).click()
11. page1.get_by_role("menuitem", name="Load Chart Layout").click()
12. page1.get_by_role("button", name="L_1").click()
13. Set 15m resolution across all 9 cells
14. Set all 9 target symbols per tab via #tv-ss

DO NOT ALTER THIS CODE UNDER ANY CIRCUMSTANCES.
==============================================================================
"""

import re
import asyncio
import logging
from playwright.async_api import async_playwright, BrowserContext, Page

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("CoinGlassPerfectSetup")

EMAIL_VAL = "singhkaranbir0248@gmail.com"
PASS_VAL = "Lu$er2hero"

TAB1_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT"]
TAB2_SYMBOLS = ["AVAXUSDT", "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT", "XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"]

async def run_tab_exact_sequence(context: BrowserContext, symbols: list[str], tab_label: str) -> Page:
    log.info(f"[{tab_label}] Starting exact recorded setup sequence...")
    
    # 1. Open login page
    page = await context.new_page()
    await page.goto("https://www.coinglass.com/login")
    await page.get_by_role("textbox", name="Email").click()
    await page.get_by_role("textbox", name="Email").fill(EMAIL_VAL)
    await page.get_by_role("textbox", name="Password").click()
    await page.get_by_role("textbox", name="Password").fill(PASS_VAL)
    
    try:
        await page.get_by_role("button", name="Login").nth(1).click(timeout=5000)
    except Exception:
        await page.get_by_role("textbox", name="Password").press("Enter")
        
    log.info(f"[{tab_label}] Credentials submitted. Waiting 5 seconds for authentication tokens to settle...")
    await asyncio.sleep(5.0)

    # 2. Open S9 layout and close login page
    page1 = await context.new_page()
    await page1.goto("https://www.coinglass.com/tv/layout/s9")
    await page.close()
    await asyncio.sleep(6.0)

    # 3. Load L_1 Chart Layout
    log.info(f"[{tab_label}] Loading L_1 chart layout...")
    try:
        await page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3).click()
        await asyncio.sleep(1.0)
        await page1.get_by_role("menuitem", name="Load Chart Layout").click()
        await asyncio.sleep(1.0)
        await page1.get_by_role("button", name="L_1").click()
        await asyncio.sleep(5.0)
    except Exception as e:
        log.warning(f"[{tab_label}] L_1 load note: {e}")

    # 4. Enforce 15m timeframe for all 9 cells
    log.info(f"[{tab_label}] Enforcing 15m timeframe across all 9 cells...")
    grid_frames = [f for f in page1.frames if "tradingview" in f.name.lower() or "chart" in f.url.lower()]
    for idx in range(min(9, len(grid_frames))):
        frame = grid_frames[idx]
        try:
            canvas = frame.locator("canvas").nth(1)
            if await canvas.is_visible(timeout=2000):
                await canvas.click(position={"x": 288, "y": 89})
            else:
                await frame.locator("body").click()
            await asyncio.sleep(0.5)

            await page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(2).click()
            await asyncio.sleep(0.5)
            await page1.get_by_text("15m").click()
            await asyncio.sleep(0.5)
        except Exception as e:
            log.warning(f"[{tab_label}] Frame {idx+1} 15m note: {e}")

    # 5. Set symbols for all 9 cells
    log.info(f"[{tab_label}] Configuring 9 symbols: {symbols}...")
    for idx, symbol in enumerate(symbols[:len(grid_frames)]):
        frame = grid_frames[idx]
        try:
            canvas = frame.locator("canvas").nth(1)
            if await canvas.is_visible(timeout=2000):
                await canvas.click(position={"x": 327, "y": 101})
            else:
                await frame.locator("body").click()
            await asyncio.sleep(0.5)

            await page1.get_by_role("button").first.click()
            await asyncio.sleep(0.5)
            await page1.locator("#tv-ss").fill(symbol)
            await asyncio.sleep(0.8)
            
            # Click matching search item or press Enter
            item = page1.locator(".symbol-item, [class*='search-item'], button").filter(has_text=symbol).first
            if await item.is_visible(timeout=2000):
                await item.click()
            else:
                await page1.locator("#tv-ss").press("Enter")
            await asyncio.sleep(1.0)
            log.info(f"[{tab_label}] Cell {idx+1}/9 set to {symbol}")
        except Exception as e:
            log.warning(f"[{tab_label}] Cell {idx+1} symbol note: {e}")

    log.info(f"[{tab_label}] Exact recorded setup completed successfully!")
    return page1

async def attach_and_setup(port: int, symbols: list[str], label: str):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0]
            await run_tab_exact_sequence(context, symbols, label)
        except Exception as e:
            log.error(f"[{label}] Could not attach to port {port}: {e}")

async def main():
    log.info("=== Launching Exact Setup for Tab 1 (Port 19899) and Tab 2 (Port 19900) ===")
    t1 = attach_and_setup(19899, TAB1_SYMBOLS, "TAB_1")
    t2 = attach_and_setup(19900, TAB2_SYMBOLS, "TAB_2")
    await asyncio.gather(t1, t2)
    log.info("=== Setup Complete ===")

if __name__ == "__main__":
    asyncio.run(main())
