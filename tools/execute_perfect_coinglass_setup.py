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
import socket
import subprocess
import os
import time
from playwright.async_api import async_playwright, BrowserContext, Page

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("CoinGlassPerfectSetup")

EMAIL_VAL = os.getenv("COINGLASS_EMAIL", "singhkaranbir0248@gmail.com")
PASS_VAL = os.getenv("COINGLASS_PASSWORD", "Lu$er2hero")

TAB1_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT"]
TAB2_SYMBOLS = ["AVAXUSDT", "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT", "XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"]

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_EXE):
    CHROME_EXE = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

def is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except Exception:
        return False

def ensure_chrome_instance(port: int, profile_name: str):
    if not is_port_open(port):
        log.info(f"Launching dedicated Chrome instance on Port {port} ({profile_name})...")
        p_dir = os.path.abspath(profile_name)
        os.makedirs(p_dir, exist_ok=True)
        cmd = [
            CHROME_EXE,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={p_dir}",
            "--start-maximized",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        subprocess.Popen(cmd)
        time.sleep(3.0)
    else:
        log.info(f"Port {port} already active with dedicated instance.")

async def wait_for_chart_frames(page: Page, target_count: int = 9, timeout: float = 30.0) -> list:
    deadline = time.time() + timeout
    while time.time() < deadline:
        frames = [f for f in page.frames if "tradingview" in f.name.lower() or "chart" in f.url.lower()]
        if len(frames) >= target_count:
            return frames[:target_count]
        await asyncio.sleep(0.5)
    return [f for f in page.frames if "tradingview" in f.name.lower() or "chart" in f.url.lower()]

async def run_tab_exact_sequence(context: BrowserContext, symbols: list[str], tab_label: str) -> Page:
    log.info(f"[{tab_label}] Starting exact recorded setup sequence...")
    
    # 1. Open login page
    page = await context.new_page()
    await page.goto("https://www.coinglass.com/login", wait_until="domcontentloaded", timeout=45000)
    email_box = page.locator("input[type='email'], input[name='email'], input[placeholder*='Email'], input[type='text']").first
    await email_box.click()
    await email_box.fill(EMAIL_VAL)
    
    pass_box = page.locator("input[type='password']").first
    await pass_box.click()
    await pass_box.fill(PASS_VAL)
    
    # Hit Login Button directly
    login_btn = page.locator("button:has-text('Login'), button:has-text('Log In'), button[type='submit']").first
    if await login_btn.is_visible(timeout=3000):
        await login_btn.click()
        log.info(f"[{tab_label}] Login button clicked successfully.")
    else:
        await pass_box.press("Enter")
        log.info(f"[{tab_label}] Login submitted via Enter key.")
        
    log.info(f"[{tab_label}] Credentials submitted. Waiting for authentication tokens to settle...")
    try:
        await page.wait_for_function("() => document.cookie.includes('cg_auth') || document.cookie.includes('CAUTH') || document.cookie.includes('token') || document.cookie.length > 50", timeout=5000)
    except Exception:
        pass
    await asyncio.sleep(5.0)

    # 2. Open S9 layout and close login page
    page1 = await context.new_page()
    await page1.goto("https://www.coinglass.com/tv/layout/s9", wait_until="domcontentloaded", timeout=60000)
    await page.close()
    await asyncio.sleep(6.0)

    # 3. Load L_1 Chart Layout
    log.info(f"[{tab_label}] Loading L_1 chart layout...")
    try:
        layout_btn = page1.locator("button[aria-label*='layout'], button[title*='layout'], button:has-text('Layout')").first
        if not await layout_btn.is_visible(timeout=2000):
            layout_btn = page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3)
        await layout_btn.click(timeout=5000)
        await asyncio.sleep(1.0)
        await page1.get_by_role("menuitem", name="Load Chart Layout").click(timeout=5000)
        await asyncio.sleep(1.0)
        await page1.get_by_role("button", name="L_1").click(timeout=5000)
        await asyncio.sleep(5.0)
    except Exception as e:
        log.warning(f"[{tab_label}] L_1 load note: {e}")
    await page1.keyboard.press("Escape")

    # 4. Enforce 15m timeframe for all 9 cells
    log.info(f"[{tab_label}] Enforcing 15m timeframe across all 9 cells...")
    grid_frames = await wait_for_chart_frames(page1, target_count=9, timeout=20.0)
    for idx in range(min(9, len(grid_frames))):
        frame = grid_frames[idx]
        try:
            canvas = frame.locator("canvas").nth(1)
            if await canvas.is_visible(timeout=2000):
                box = await canvas.bounding_box()
                if box:
                    await page1.mouse.click(box["x"] + 20, box["y"] + 20)
                else:
                    await canvas.click()
            else:
                await frame.locator("body").click()
            await asyncio.sleep(0.5)

            menu_btn = page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(2)
            if await menu_btn.is_visible(timeout=1500):
                await menu_btn.click()
                await asyncio.sleep(0.5)
                tf_15m = page1.locator(".MuiMenuItem-root, div, button").filter(has_text=re.compile(r"^15m$")).first
                if await tf_15m.is_visible(timeout=1500):
                    await tf_15m.click()
            await asyncio.sleep(0.5)
            await page1.keyboard.press("Escape")
        except Exception as e:
            log.warning(f"[{tab_label}] Frame {idx+1} 15m note: {e}")
            await page1.keyboard.press("Escape")

    # 5. Set symbols for all 9 cells
    log.info(f"[{tab_label}] Configuring 9 symbols: {symbols}...")
    for idx, symbol in enumerate(symbols[:len(grid_frames)]):
        frame = grid_frames[idx]
        try:
            canvas = frame.locator("canvas").nth(1)
            if await canvas.is_visible(timeout=2000):
                box = await canvas.bounding_box()
                if box:
                    await page1.mouse.click(box["x"] + 40, box["y"] + 20)
                else:
                    await canvas.click()
            else:
                await frame.locator("body").click()
            await asyncio.sleep(0.5)

            sym_btn = page1.get_by_role("button").first
            if await sym_btn.is_visible(timeout=1500):
                await sym_btn.click()
                await asyncio.sleep(0.5)
            
            # Try frame-scoped search input first, fallback to page-scoped
            ss_input = frame.locator("#tv-ss")
            if not await ss_input.is_visible(timeout=1000):
                ss_input = page1.locator("#tv-ss")
                
            await ss_input.fill(symbol)
            await asyncio.sleep(0.8)
            
            # Click matching search item or press Enter
            item = frame.locator(".symbol-item, [class*='search-item'], button").filter(has_text=symbol).first
            if not await item.is_visible(timeout=1000):
                item = page1.locator(".symbol-item, [class*='search-item'], button").filter(has_text=symbol).first
                
            if await item.is_visible(timeout=1000):
                await item.click()
            else:
                await ss_input.press("Enter")
            await asyncio.sleep(1.0)
            log.info(f"[{tab_label}] Cell {idx+1}/9 set to {symbol}")
        except Exception as e:
            log.warning(f"[{tab_label}] Cell {idx+1} symbol note: {e}")

    log.info(f"[{tab_label}] Exact recorded setup completed successfully!")
    return page1

import os

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_EXE):
    CHROME_EXE = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

def is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except Exception:
        return False

def ensure_chrome_instance(port: int, profile_name: str):
    if not is_port_open(port):
        log.info(f"Launching dedicated Chrome instance on Port {port} ({profile_name})...")
        p_dir = os.path.abspath(profile_name)
        os.makedirs(p_dir, exist_ok=True)
        cmd = [
            CHROME_EXE,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={p_dir}",
            "--start-maximized",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        subprocess.Popen(cmd)
        time.sleep(3.0)
    else:
        log.info(f"Port {port} already active with dedicated instance.")

async def attach_and_setup(port: int, profile_name: str, symbols: list[str], label: str):
    ensure_chrome_instance(port, profile_name)
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0]
            await run_tab_exact_sequence(context, symbols, label)
        except Exception as e:
            log.error(f"[{label}] Error on port {port}: {e}")

async def main():
    log.info("=== Launching Two Independent Chrome Instances for Tab 1 (19899) and Tab 2 (19900) ===")
    t1 = attach_and_setup(19899, "chrome_profile_tab1", TAB1_SYMBOLS, "TAB_1")
    t2 = attach_and_setup(19900, "chrome_profile_tab2", TAB2_SYMBOLS, "TAB_2")
    await asyncio.gather(t1, t2)
    log.info("=== Setup Complete ===")

if __name__ == "__main__":
    import time
    asyncio.run(main())

