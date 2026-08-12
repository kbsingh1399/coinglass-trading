#!/usr/bin/env python3
"""
Isolated Linux Chrome Sandbox Test
===================================
Tests the browser launch pipeline in a Linux container environment
without affecting the Windows headful configuration in Engine_1.py.

Usage:
    python3 test_linux_browser.py

Commit under test: 6cce8e4 (master)
"""

import asyncio
import sys
import os
import time

# ─── Configuration ───────────────────────────────────────────────────
TEST_URL = "https://www.coinglass.com"
TIMEOUT_MS = 30000
USER_DATA_DIR = os.path.join(os.getcwd(), "chrome_profile_linux_test")

# ─── OS Detection (mirrors Engine_1.py L3726-3727) ──────────────────
is_linux = sys.platform.startswith("linux")
headless_flag = is_linux or os.environ.get("HEADLESS", "0") == "1"

print(f"[Config] Platform: {sys.platform}")
print(f"[Config] is_linux: {is_linux}")
print(f"[Config] headless: {headless_flag}")


async def test_linux_launch():
    """Launch Chromium with Linux container flags and verify Coinglass loads."""
    from playwright.async_api import async_playwright

    os.makedirs(USER_DATA_DIR, exist_ok=True)

    # ─── Chrome args (mirrors Engine_1.py L3728-3740) ───────────────
    chrome_args = [
        "--disable-features=CalculateNativeWinOcclusion",
        "--disable-background-timer-throttling",
        "--remote-debugging-port=9223",  # Different port to avoid conflicts
    ]
    if is_linux:
        chrome_args.extend([
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ])

    print(f"[Linux Test] Chrome args: {chrome_args}")

    async with async_playwright() as pw:
        print("[Linux Test] Launching Chromium with persistent context...")
        t0 = time.time()

        ctx = await pw.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=headless_flag,
            viewport={"width": 1920, "height": 1080},
            args=chrome_args,
        )

        launch_time = time.time() - t0
        print(f"[Linux Test] Chromium launched in {launch_time:.1f}s")

        page = await ctx.new_page()

        # ─── Test 1: Navigate to Coinglass ──────────────────────────
        print(f"[Linux Test] Navigating to {TEST_URL}...")
        t1 = time.time()
        try:
            response = await page.goto(TEST_URL, wait_until="load", timeout=TIMEOUT_MS)
            nav_time = time.time() - t1
            status = response.status if response else "no response"
            print(f"[Linux Test] ✅ Page loaded in {nav_time:.1f}s (HTTP {status})")
        except Exception as e:
            nav_time = time.time() - t1
            print(f"[Linux Test] ❌ Navigation failed after {nav_time:.1f}s: {e}")

        # ─── Test 2: Check page title ───────────────────────────────
        title = await page.title()
        print(f"[Linux Test] Page title: '{title}'")

        # ─── Test 3: Check for key elements ─────────────────────────
        body_text = await page.inner_text("body")
        has_content = len(body_text) > 100
        print(f"[Linux Test] Body text length: {len(body_text)} chars ({'✅' if has_content else '❌'})")

        # ─── Test 4: Screenshot ──────────────────────────────────────
        ss_path = os.path.join(os.getcwd(), "test_linux_screenshot.png")
        await page.screenshot(path=ss_path)
        ss_size = os.path.getsize(ss_path) if os.path.exists(ss_path) else 0
        print(f"[Linux Test] Screenshot saved: {ss_path} ({ss_size:,} bytes)")

        # ─── Test 5: JavaScript execution ───────────────────────────
        js_result = await page.evaluate("() => ({ ua: navigator.userAgent, platform: navigator.platform })")
        print(f"[Linux Test] User-Agent: {js_result.get('ua', 'N/A')[:80]}...")
        print(f"[Linux Test] JS Platform: {js_result.get('platform', 'N/A')}")

        await ctx.close()

    # ─── Summary ─────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  TEST RESULTS SUMMARY")
    print("=" * 70)
    results = {
        "Chromium launch": launch_time < 15,
        "Page navigation": nav_time < TIMEOUT_MS / 1000,
        "Page content": has_content,
        "Screenshot capture": ss_size > 0,
        "JS execution": bool(js_result.get("ua")),
    }
    all_pass = all(results.values())
    for name, passed in results.items():
        print(f"  {'✅' if passed else '❌'} {name}")
    print(f"\n  {'🎉 ALL TESTS PASSED' if all_pass else '❌ SOME TESTS FAILED'}")
    print("=" * 70)

    return all_pass


if __name__ == "__main__":
    success = asyncio.run(test_linux_launch())
    sys.exit(0 if success else 1)
