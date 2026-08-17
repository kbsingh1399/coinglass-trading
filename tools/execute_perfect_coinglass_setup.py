"""
==============================================================================
⛔ CRITICAL ARCHITECTURAL INVARIANT — DO NOT MODIFY OR REFACTOR THIS FLOW
==============================================================================
This module contains the exact, user-verified, recorded Playwright sequence to:
1. Authenticate to CoinGlass via https://www.coinglass.com/login
2. Open S9 layout at https://www.coinglass.com/tv/layout/s9 and close login tab
3. Load the custom 'L_1' layout preset via the top-bar dropdown menu
4. Focus each grid iframe and enforce the '15m' timeframe
5. Set all 9 target symbols per tab via the TV symbol search modal (#tv-ss)

DO NOT ALTER BUTTON INDICES, TIMEFRAME CLICKS, OR NAVIGATION SEQUENCING.
==============================================================================
"""

import re
import asyncio
import logging
from playwright.async_api import async_playwright, Page, BrowserContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("CoinGlassPerfectSetup")

EMAIL_VAL = "singhkaranbir0248@gmail.com"
PASS_VAL = "Lu$er2hero"

TAB1_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT"]
TAB2_SYMBOLS = ["AVAXUSDT", "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT", "XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"]

async def execute_tab_setup(port: int, symbols: list[str], tab_name: str) -> bool:
    endpoint_url = f"http://127.0.0.1:{port}"
    log.info(f"[{tab_name}] Connecting over CDP to port {port}...")
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(endpoint_url)
        except Exception as e:
            log.error(f"[{tab_name}] Failed to connect to port {port}: {e}")
            return False

        context = browser.contexts[0]
        
        # 1. Login sequence
        log.info(f"[{tab_name}] Navigating to login page...")
        login_page = await context.new_page()
        await login_page.goto("https://www.coinglass.com/login", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2.0)
        
        try:
            email_field = login_page.get_by_role("textbox", name="Email")
            if await email_field.is_visible(timeout=3000):
                log.info(f"[{tab_name}] Filling login credentials...")
                await email_field.click()
                await email_field.fill(EMAIL_VAL)
                pass_field = login_page.get_by_role("textbox", name="Password")
                await pass_field.click()
                await pass_field.fill(PASS_VAL)
                await login_page.get_by_role("button", name="Login").nth(1).click()
                await asyncio.sleep(4.0)
        except Exception as e:
            log.info(f"[{tab_name}] Auth check notice: {e}")

        # 2. Open S9 layout in new tab and close login page
        log.info(f"[{tab_name}] Opening S9 layout...")
        s9_page = await context.new_page()
        await s9_page.goto("https://www.coinglass.com/tv/layout/s9", wait_until="domcontentloaded", timeout=60000)
        await login_page.close()
        await asyncio.sleep(6.0)

        # 3. Load L_1 Layout
        log.info(f"[{tab_name}] Triggering L_1 chart layout load...")
        try:
            layout_btn = s9_page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3)
            if await layout_btn.is_visible(timeout=5000):
                await layout_btn.click()
                await asyncio.sleep(1.0)
                await s9_page.get_by_role("menuitem", name="Load Chart Layout").click()
                await asyncio.sleep(1.0)
                await s9_page.get_by_role("button", name="L_1").click()
                log.info(f"[{tab_name}] L_1 preset selected.")
                await asyncio.sleep(5.0)
        except Exception as le:
            log.warning(f"[{tab_name}] L_1 load note: {le}")

        # 4. Enforce 15m timeframe on all 9 frames
        log.info(f"[{tab_name}] Enforcing 15m timeframe across all 9 grid frames...")
        iframes = s9_page.frames
        grid_frames = [f for f in iframes if "tradingview" in f.name.lower() or "chart" in f.url.lower()]
        log.info(f"[{tab_name}] Detected {len(grid_frames)} iframe chart frames.")

        for idx in range(min(9, len(grid_frames))):
            frame = grid_frames[idx]
            try:
                # Focus canvas
                canvas = frame.locator("canvas").nth(1)
                if await canvas.is_visible(timeout=2000):
                    await canvas.click(position={"x": 280, "y": 90})
                else:
                    await frame.locator("body").click()
                await asyncio.sleep(0.5)

                # Click timeframe dropdown and select 15m
                timeframe_btn = s9_page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(2)
                if await timeframe_btn.is_visible(timeout=2000):
                    await timeframe_btn.click()
                    await asyncio.sleep(0.5)
                    btn_15m = s9_page.get_by_text("15m")
                    if await btn_15m.is_visible(timeout=2000):
                        await btn_15m.click()
                        log.info(f"[{tab_name}] Frame {idx+1}/9 locked to 15m.")
                        await asyncio.sleep(0.5)
            except Exception as fe:
                log.warning(f"[{tab_name}] Frame {idx+1} timeframe note: {fe}")

        # 5. Set target symbols for all 9 cells
        log.info(f"[{tab_name}] Configuring target symbols: {symbols}...")
        for idx, symbol in enumerate(symbols[:len(grid_frames)]):
            frame = grid_frames[idx]
            try:
                # Focus cell
                canvas = frame.locator("canvas").nth(1)
                if await canvas.is_visible(timeout=2000):
                    await canvas.click(position={"x": 300, "y": 80})
                else:
                    await frame.locator("body").click()
                await asyncio.sleep(0.5)

                # Open symbol search modal
                sym_btn = s9_page.get_by_role("button").first
                if await sym_btn.is_visible(timeout=2000):
                    await sym_btn.click()
                    await asyncio.sleep(0.5)

                    search_input = s9_page.locator("#tv-ss")
                    if await search_input.is_visible(timeout=2000):
                        await search_input.fill(symbol)
                        await asyncio.sleep(0.8)
                        
                        # Click the top matching Binance result
                        result_btn = s9_page.locator(".symbol-item, [class*='search-item'], button").filter(has_text=symbol).first
                        if await result_btn.is_visible(timeout=2000):
                            await result_btn.click()
                            log.info(f"[{tab_name}] Cell {idx+1}/9 assigned to {symbol}.")
                        else:
                            await search_input.press("Enter")
                            log.info(f"[{tab_name}] Cell {idx+1}/9 assigned to {symbol} via Enter.")
                        await asyncio.sleep(1.0)
            except Exception as se:
                log.warning(f"[{tab_name}] Cell {idx+1} symbol config note: {se}")

        log.info(f"[{tab_name}] Full setup and symbol configuration complete on port {port}!")
        return True

async def main():
    log.info("=== Starting Perfect Dual-Tab Setup Sequence ===")
    t1 = execute_tab_setup(19899, TAB1_SYMBOLS, "TAB_1")
    t2 = execute_tab_setup(19900, TAB2_SYMBOLS, "TAB_2")
    await asyncio.gather(t1, t2)
    log.info("=== Dual-Tab Setup Sequence Finished ===")

if __name__ == "__main__":
    asyncio.run(main())
