import asyncio
import os
import sys
import time
import subprocess
from playwright.async_api import async_playwright

artifact_dir = r"C:\Users\SIGMA\.gemini\antigravity-ide\brain\dd6ec775-a34b-473e-a805-4f15fa8ce226"
os.makedirs(artifact_dir, exist_ok=True)

async def capture_chrome_screenshots():
    """Captures high-resolution screenshots of both TAB_1 (9222) and TAB_2 (19900)."""
    screenshots = {}
    async with async_playwright() as p:
        for port, tab_name in [(9222, "TAB_1"), (19900, "TAB_2"), (19899, "TAB_1_LEGACY")]:
            try:
                browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=4000)
                for ctx in browser.contexts:
                    for idx, page in enumerate(ctx.pages):
                        title = await page.title()
                        file_name = f"chrome_audit_{tab_name.lower()}_p{idx}.png"
                        out_path = os.path.join(artifact_dir, file_name)
                        await page.screenshot(path=out_path, full_page=False)
                        screenshots[f"{tab_name}_p{idx}"] = {
                            "port": port,
                            "title": title,
                            "url": page.url,
                            "screenshot_path": out_path,
                            "frames": len(page.frames)
                        }
                await browser.close()
            except Exception as e:
                # Tab not reachable on this port
                pass
    return screenshots

async def main():
    print("[Live Verifier] Checking for active Chrome instances...")
    shots = await capture_chrome_screenshots()
    print(f"[Live Verifier] Captured {len(shots)} active Chrome screenshots:")
    for k, v in shots.items():
        print(f" - {k} (Port {v['port']}): '{v['title']}' -> {v['screenshot_path']} ({v['frames']} frames)")
    return shots

if __name__ == "__main__":
    asyncio.run(main())
