import re
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        
        print("Navigating to login page...")
        await page.goto("https://www.coinglass.com/login")
        await page.wait_for_timeout(2000)
        
        print("Filling credentials...")
        await page.get_by_role("textbox", name="Email").click()
        await page.get_by_role("textbox", name="Email").fill("singhkaranbir0248@gmail.com")
        await page.get_by_role("textbox", name="Email").press("Tab")
        await page.get_by_role("textbox", name="Password").click()
        await page.get_by_role("textbox", name="Password").fill("Lu$er2hero")
        
        print("Clicking login...")
        await page.get_by_role("button", name="Login").nth(1).click()
        await page.wait_for_timeout(5000) # Wait for login redirect/cookies
        
        print("Opening s9 layout...")
        page1 = await context.new_page()
        await page1.goto("https://www.coinglass.com/tv/layout/s9")
        await page1.wait_for_timeout(10000)
        
        print("Loading layout 'L_1'...")
        # nth(3) button for layout settings
        try:
            await page1.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3).click()
            await page1.get_by_role("menuitem", name="Load Chart Layout").click()
            await page1.get_by_role("button", name="L_1").click()
            await page1.wait_for_timeout(5000)
            print("Successfully loaded layout L_1!")
        except Exception as e:
            print("Error loading layout:", e)
            
        # Take a screenshot to verify
        path = "C:\\Users\\SIGMA\\.gemini\\antigravity\\brain\\b0378007-cf33-45a3-a901-d12ca2793e08\\verification_recorded.png"
        await page1.screenshot(path=path)
        print("Screenshot saved to:", path)
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
