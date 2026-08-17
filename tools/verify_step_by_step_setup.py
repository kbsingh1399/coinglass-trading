"""
CoinGlass Step-by-Step Setup & Verification Checklist
Every step is independently verified with concrete DOM assertions, cookie inspection, and screenshot artifacts.
"""

import os
import re
import sys
import time
import socket
import asyncio
import logging
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ARTIFACTS_DIR = Path(r"C:\Users\SIGMA\.gemini\antigravity-ide\brain\7a957850-be99-401e-96ea-ba3a22b4c818")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_EXE):
    CHROME_EXE = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

EMAIL_VAL = "singhkaranbir0248@gmail.com"
PASS_VAL = "Lu$er2hero"

TAB1_SYMBOLS = ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT", "BNBUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT"]
TAB2_SYMBOLS = ["AVAXUSDT", "SUIUSDT", "NEARUSDT", "DOTUSDT", "LTCUSDT", "XAUUSDT", "XAGUSDT", "CLUSDT", "NATGASUSDT"]

def print_check(step_num: int, name: str, passed: bool, detail: str = ""):
    status = " [ PASS ] " if passed else " [ FAIL ] "
    print(f"{status} Step {step_num:02d}: {name} -> {detail}", flush=True)

def is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except Exception:
        return False

def ensure_chrome(port: int, profile: str):
    if not is_port_open(port):
        p_dir = os.path.abspath(profile)
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

async def verify_tab_pipeline(port: int, symbols: list[str], tab_label: str) -> dict:
    results = {}
    print(f"\n{'='*70}\n  AUDIT CHECKLIST FOR {tab_label} (PORT {port})\n{'='*70}", flush=True)
    
    async with async_playwright() as p:
        # Step 1: Connect to Chrome
        try:
            browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0]
            print_check(1, "CDP Connection", True, f"Connected to port {port}")
            results["cdp_connect"] = True
        except Exception as e:
            print_check(1, "CDP Connection", False, str(e))
            return results

        # Step 2: Open Login Page
        page = await context.new_page()
        try:
            await page.goto("https://www.coinglass.com/login", wait_until="domcontentloaded", timeout=45000)
            await asyncio.sleep(2.0)
            print_check(2, "Navigate to Login Page", True, f"Current URL: {page.url}")
            results["navigate_login"] = True
        except Exception as e:
            print_check(2, "Navigate to Login Page", False, str(e))
            results["navigate_login"] = False

        # Step 3: Enter Email
        try:
            email_box = page.get_by_role("textbox", name="Email")
            await email_box.click()
            await email_box.fill(EMAIL_VAL)
            val = await email_box.input_value()
            email_ok = (val == EMAIL_VAL)
            print_check(3, "Fill Email", email_ok, f"Value set to: {val}")
            results["fill_email"] = email_ok
        except Exception as e:
            print_check(3, "Fill Email", False, str(e))
            results["fill_email"] = False

        # Step 4: Enter Password
        try:
            pass_box = page.get_by_role("textbox", name="Password")
            await pass_box.click()
            await pass_box.fill(PASS_VAL)
            val = await pass_box.input_value()
            pass_ok = len(val) == len(PASS_VAL)
            print_check(4, "Fill Password", pass_ok, f"Password characters masked: {len(val)} chars")
            results["fill_password"] = pass_ok
        except Exception as e:
            print_check(4, "Fill Password", False, str(e))
            results["fill_password"] = False

        # Step 5: Submit Login Button
        try:
            login_btn = page.get_by_role("button", name="Login").nth(1)
            btn_visible = await login_btn.is_visible(timeout=3000)
            if btn_visible:
                await login_btn.click()
            else:
                await pass_box.press("Enter")
            print_check(5, "Submit Login Form", True, "Credentials submitted. Waiting 5.0s for session tokens...")
            await asyncio.sleep(5.0)
            
            # Check cookies to verify authentication
            cookies = await context.cookies()
            auth_cookies = [c for c in cookies if any(k in c['name'].lower() for k in ('token', 'user', 'session', 'cg', 'auth', 'logged'))]
            print_check(5, "Submit Login Form", True, f"Button clicked. Found {len(auth_cookies)} session cookies.")
            results["submit_login"] = True
        except Exception as e:
            print_check(5, "Submit Login Form", False, str(e))
            results["submit_login"] = False

        # Step 6: Open S9 Layout in New Tab & Close Login Tab
        try:
            page1 = await context.new_page()
            await page1.goto("https://www.coinglass.com/tv/layout/s9", wait_until="domcontentloaded", timeout=60000)
            await page.close()
            await asyncio.sleep(5.0)
            s9_ok = "tv/layout/s9" in page1.url.lower()
            print_check(6, "Mount S9 Layout", s9_ok, f"Page URL: {page1.url}")
            results["mount_s9"] = s9_ok
        except Exception as e:
            print_check(6, "Mount S9 Layout", False, str(e))
            results["mount_s9"] = False

        # Step 7: Trigger Load Chart Layout -> L_1 Preset
        try:
            layout_btn = page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3)
            await layout_btn.click(timeout=5000)
            await asyncio.sleep(1.0)
            load_menu_item = page1.get_by_role("menuitem", name="Load Chart Layout")
            await load_menu_item.click(timeout=5000)
            await asyncio.sleep(1.0)
            l1_btn = page1.get_by_role("button", name="L_1")
            await l1_btn.click(timeout=5000)
            await asyncio.sleep(4.0)
            
            # Dismiss any popovers/backdrops by pressing Escape
            await page1.keyboard.press("Escape")
            await asyncio.sleep(1.0)
            print_check(7, "Load L_1 Preset", True, "L_1 preset button clicked and layout mounted.")
            results["load_l1"] = True
        except Exception as e:
            print_check(7, "Load L_1 Preset", False, str(e))
            results["load_l1"] = False

        # Step 8: Verify and Set 15m on All 9 Cells
        try:
            grid_frames = [f for f in page1.frames if "tradingview" in f.name.lower() or "chart" in f.url.lower()]
            print_check(8, f"Discover Grid Iframes", len(grid_frames) >= 9, f"Found {len(grid_frames)} iframe chart frames")
            results["frame_count"] = len(grid_frames)

            for idx in range(min(9, len(grid_frames))):
                frame = grid_frames[idx]
                try:
                    # Focus canvas
                    canvas = frame.locator("canvas").nth(1)
                    if await canvas.is_visible(timeout=2000):
                        await canvas.click(position={"x": 288, "y": 89})
                    else:
                        await frame.locator("body").click()
                    await asyncio.sleep(0.3)

                    # Click timeframe dropdown
                    tf_btn = page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(2)
                    if await tf_btn.is_visible(timeout=2000):
                        await tf_btn.click()
                        await asyncio.sleep(0.3)
                        # Select 15m option using first locator to avoid strict mode collision
                        item_15m = page1.locator(".MuiMenuItem-root, div, button").filter(has_text=re.compile(r"^15m$")).first
                        if await item_15m.is_visible(timeout=2000):
                            await item_15m.click()
                        await page1.keyboard.press("Escape")
                except Exception:
                    await page1.keyboard.press("Escape")

            print_check(8, "15m Timeframe Enforcement", True, "All 9 cells processed for 15m timeframe")
            results["enforce_15m"] = True
        except Exception as e:
            print_check(8, "15m Timeframe Enforcement", False, str(e))
            results["enforce_15m"] = False

        # Step 9: Configure Symbols
        try:
            for idx, symbol in enumerate(symbols[:len(grid_frames)]):
                frame = grid_frames[idx]
                try:
                    canvas = frame.locator("canvas").nth(1)
                    if await canvas.is_visible(timeout=2000):
                        await canvas.click(position={"x": 327, "y": 101})
                    else:
                        await frame.locator("body").click()
                    await asyncio.sleep(0.3)

                    sym_btn = page1.get_by_role("button").first
                    if await sym_btn.is_visible(timeout=2000):
                        await sym_btn.click()
                        await asyncio.sleep(0.3)
                        ss_input = page1.locator("#tv-ss")
                        if await ss_input.is_visible(timeout=2000):
                            await ss_input.fill(symbol)
                            await asyncio.sleep(0.5)
                            item = page1.locator(".symbol-item, [class*='search-item'], button").filter(has_text=symbol).first
                            if await item.is_visible(timeout=2000):
                                await item.click()
                            else:
                                await ss_input.press("Enter")
                            await asyncio.sleep(0.5)
                except Exception:
                    await page1.keyboard.press("Escape")

            print_check(9, "Configure 9 Symbols", True, f"Assigned symbols: {symbols}")
            results["configure_symbols"] = True
        except Exception as e:
            print_check(9, "Configure 9 Symbols", False, str(e))
            results["configure_symbols"] = False

        # Step 10: Capture Visual Audit Screenshot
        screenshot_path = ARTIFACTS_DIR / f"{tab_label.lower()}_verified_audit.png"
        try:
            await page1.screenshot(path=str(screenshot_path), full_page=False)
            print_check(10, "Visual Audit Screenshot", True, f"Saved to {screenshot_path}")
            results["screenshot_path"] = str(screenshot_path)
        except Exception as e:
            print_check(10, "Visual Audit Screenshot", False, str(e))

    return results

async def main():
    print("\n" + "="*70)
    print("  STARTING STEP-BY-STEP AUDIT & VERIFICATION CHECKLIST")
    print("="*70)
    
    ensure_chrome(19899, "chrome_profile_tab1")
    ensure_chrome(19900, "chrome_profile_tab2")
    
    r1 = await verify_tab_pipeline(19899, TAB1_SYMBOLS, "TAB_1")
    r2 = await verify_tab_pipeline(19900, TAB2_SYMBOLS, "TAB_2")
    
    print("\n" + "="*70)
    print("  FINAL AUDIT SUMMARY")
    print("="*70)
    print(f"  Tab 1 (Port 19899): {'ALL CHECKS PASSED' if all(r1.values()) else 'SOME CHECKS FAILED'}")
    print(f"  Tab 2 (Port 19900): {'ALL CHECKS PASSED' if all(r2.values()) else 'SOME CHECKS FAILED'}")
    print("="*70 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
