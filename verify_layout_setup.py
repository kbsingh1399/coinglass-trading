import re
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        print("Connecting to browser on port 19899...")
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:19899")
            context = browser.contexts[0]
        except Exception as e:
            print("Failed to connect to 19899:", e)
            return

        page = context.pages[0]
        print("Attached to page:", page.url)

        # Make sure layout page is open
        if "layout" not in page.url:
            print("Navigating to s9 layout...")
            await page.goto("https://www.coinglass.com/tv/layout/s9")
            await asyncio.sleep(5.0)

        # Load L_1 layout first
        try:
            layout_btn = page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3)
            if await layout_btn.is_visible(timeout=5000):
                print("Loading L_1 layout...")
                await layout_btn.click()
                await page.get_by_role("menuitem", name="Load Chart Layout").click()
                await page.get_by_role("button", name="L_1").click()
                await asyncio.sleep(5.0)
        except Exception as le:
            print("L_1 load bypassed/failed:", le)

        # Configure cell 1 (BTCUSDT) and cell 2 (ETHUSDT) as a test
        test_symbols = ["BTCUSDT", "ETHUSDT"]
        
        for i, sym in enumerate(test_symbols):
            print(f"Configuring cell {i+1} to {sym}...")
            try:
                # Focus iframe body directly without pixel coordinates
                container_id = f"tv_chart_container_win{i+1}"
                selector = f"#{container_id} iframe" if i > 0 else "#tv_chart_container_win1 iframe, #tv_chart_container_main iframe"
                iframe = page.locator(selector).first
                frame = iframe.content_frame
                if frame:
                    await frame.locator("body").focus()
                await asyncio.sleep(0.5)

                # Set resolution to 15m
                await page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(2).click()
                await asyncio.sleep(0.5)
                try:
                    await page.get_by_text("15m").first.click()
                except Exception:
                    await page.locator("div").filter(has_text="15m").nth(2).click()
                await asyncio.sleep(0.5)

                # Change symbol
                await page.get_by_role("button").first.click()
                await asyncio.sleep(0.5)
                
                await page.locator("#tv-ss").fill(sym)
                await asyncio.sleep(1.0)
                
                result_btn = page.get_by_role("button", name=re.compile(f"Binance {sym}", re.I)).first
                await result_btn.click()
                await asyncio.sleep(2.0)
                print(f"Cell {i+1} configured successfully!")
            except Exception as ce:
                print(f"Cell {i+1} failed:", ce)

        # Take a screenshot to verify
        path = "C:\\Users\\SIGMA\\.gemini\\antigravity\\brain\\b0378007-cf33-45a3-a901-d12ca2793e08\\layout_verify_screenshot.png"
        await page.screenshot(path=path)
        print("Screenshot saved to:", path)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
