import asyncio
import os
from playwright.async_api import async_playwright

async def capture_screenshots():
    ports = [9222, 9223, 9224]  # Engine uses sequential ports starting at 9222
    output_dir = r"C:\Users\SIGMA\.gemini\antigravity\brain\b0378007-cf33-45a3-a901-d12ca2793e08\scratch"
    os.makedirs(output_dir, exist_ok=True)
    
    async with async_playwright() as p:
        for port in ports:
            try:
                # Try to connect to the remote debugging port
                browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=3000)
                
                # Get the first context and page
                context = browser.contexts[0]
                if not context.pages:
                    print(f"[Port {port}] Connected, but no pages open.")
                    continue
                
                page = context.pages[0]
                title = await page.title()
                print(f"[Port {port}] Connected to page: {title}")
                
                # Take screenshot
                screenshot_path = os.path.join(output_dir, f"engine_screenshot_port_{port}.png")
                await page.screenshot(path=screenshot_path, full_page=True)
                print(f"[Port {port}] Screenshot saved to {screenshot_path}")
                
                await browser.close()
            except Exception as e:
                print(f"[Port {port}] Could not connect or capture: {e}")

if __name__ == "__main__":
    asyncio.run(capture_screenshots())
