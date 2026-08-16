import asyncio
import os
import re
import sys
from playwright.async_api import async_playwright

async def render_svg_to_png():
    artifact_dir = r"C:\Users\SIGMA\.gemini\antigravity\brain\b0378007-cf33-45a3-a901-d12ca2793e08"
    svg_path = os.path.join(artifact_dir, "terminal_dashboard_live.svg")
    png_path = os.path.join(artifact_dir, "terminal_dashboard_live.png")
    
    if not os.path.exists(svg_path):
        print(f"File {svg_path} does not exist")
        return

    with open(svg_path, "r", encoding="utf-8") as f:
        svg_content = f.read()

    # Replace remote font URLs with local system monospace to prevent network hang
    svg_content_clean = re.sub(r'url\("https://cdnjs\.cloudflare\.com/[^"]+"\)', 'local("Consolas")', svg_content)
    
    clean_svg_path = os.path.join(artifact_dir, "terminal_dashboard_clean.svg")
    with open(clean_svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content_clean)

    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 2100, "height": 1450})
        await page.goto(f"file:///{clean_svg_path.replace(os.sep, '/')}", wait_until="domcontentloaded")
        await page.screenshot(path=png_path, timeout=5000)
        await browser.close()
        print(f"[OK] Terminal dashboard SVG rendered to PNG at {png_path}")

if __name__ == "__main__":
    asyncio.run(render_svg_to_png())
