#!/usr/bin/env python3
"""
System Chromium Test — Bypasses Playwright CDN using system-installed Chromium.
Uses executable_path to point Playwright at /usr/bin/chromium-browser.

Usage (Linux with system Chromium):
    python test_system_chromium.py

Usage (Windows with Chrome):
    python test_system_chromium.py
"""

import asyncio
import os
import sys
import shutil
import platform

# ─── Find System Browser ─────────────────────────────────────────────
def find_system_chromium():
    """Locate system-installed Chromium/Chrome binary."""
    candidates = []
    
    if sys.platform.startswith("linux"):
        candidates = [
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/snap/bin/chromium",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
        ]
    elif sys.platform == "win32":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    elif sys.platform == "darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    
    # Also check PATH
    for name in ["chromium-browser", "chromium", "google-chrome", "chrome"]:
        found = shutil.which(name)
        if found:
            candidates.insert(0, found)
    
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    
    return None


async def test_system_chromium():
    """Launch system Chromium via Playwright and verify Coinglass loads."""
    from playwright.async_api import async_playwright

    chrome_path = find_system_chromium()
    
    if not chrome_path:
        print("❌ No system Chromium/Chrome found!")
        print("   Install with: sudo apt install chromium-browser")
        print("   Or:           sudo apt install chromium")
        return False
    
    print(f"[System Chromium] Found executable: {chrome_path}")
    print(f"[System Chromium] Platform: {sys.platform}")
    print(f"[System Chromium] File size: {os.path.getsize(chrome_path) / 1024 / 1024:.1f} MB")

    is_linux = sys.platform.startswith("linux")
    user_data_dir = os.path.join(os.getcwd(), "chrome_profile_system_test")
    os.makedirs(user_data_dir, exist_ok=True)

    chrome_args = [
        "--disable-features=CalculateNativeWinOcclusion",
        "--disable-background-timer-throttling",
        "--remote-debugging-port=9223",
    ]
    if is_linux:
        chrome_args.extend([
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ])

    async with async_playwright() as pw:
        print(f"[System Chromium] Launching with executable_path={chrome_path}")
        
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir,
            executable_path=chrome_path,      # ← BYPASSES Playwright CDN!
            headless=is_linux,
            viewport={"width": 1920, "height": 1080},
            args=chrome_args,
        )

        page = await ctx.new_page()
        
        # Test 1: Navigate to Coinglass
        print(f"[System Chromium] Navigating to https://www.coinglass.com ...")
        try:
            response = await page.goto("https://www.coinglass.com", wait_until="load", timeout=30000)
            status = response.status if response else "no response"
            print(f"[System Chromium] ✅ Page loaded! HTTP {status}")
        except Exception as e:
            print(f"[System Chromium] ❌ Navigation failed: {e}")
            await ctx.close()
            return False

        # Test 2: Page title
        title = await page.title()
        print(f"[System Chromium] Page title: '{title}'")

        # Test 3: Screenshot
        ss_path = os.path.join(os.getcwd(), "test_system_chromium_screenshot.png")
        await page.screenshot(path=ss_path)
        print(f"[System Chromium] Screenshot saved: {ss_path}")

        # Test 4: JS execution
        js_info = await page.evaluate("() => ({ ua: navigator.userAgent, platform: navigator.platform })")
        print(f"[System Chromium] User-Agent: {js_info.get('ua', 'N/A')[:80]}...")

        await ctx.close()

    print("\n" + "=" * 70)
    print("  🎉 SYSTEM CHROMIUM TEST PASSED")
    print("  Playwright CDN bypass successful via executable_path")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_system_chromium())
    sys.exit(0 if success else 1)
