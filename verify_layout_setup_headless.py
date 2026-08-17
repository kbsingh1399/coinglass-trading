import re
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        print("Launching Chromium headless...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()

        print("Navigating to login...")
        await page.goto("https://www.coinglass.com/login")
        await page.wait_for_timeout(2000)

        print("Filling credentials...")
        await page.get_by_role("textbox", name="Email").click()
        await page.get_by_role("textbox", name="Email").fill("singhkaranbir0248@gmail.com")
        await page.get_by_role("textbox", name="Password").click()
        await page.get_by_role("textbox", name="Password").fill("Lu$er2hero")
        
        print("Clicking login...")
        await page.get_by_role("button", name="Login").nth(1).click()
        await page.wait_for_timeout(5000)

        print("Navigating to layout...")
        await page.goto("https://www.coinglass.com/tv/layout/s9")
        await page.wait_for_timeout(10000)

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
