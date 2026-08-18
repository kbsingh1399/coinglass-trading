import asyncio
import os
import sys
import json
import time
from playwright.async_api import async_playwright

async def review_chrome_instances():
    ports = [19899, 19900, 9222, 9223]
    artifact_dir = r"C:\Users\SIGMA\.gemini\antigravity-ide\brain\dd6ec775-a34b-473e-a805-4f15fa8ce226"
    os.makedirs(artifact_dir, exist_ok=True)
    
    results = {}
    
    async with async_playwright() as p:
        for port in ports:
            try:
                browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=4000)
                results[f"port_{port}"] = []
                for ctx_idx, ctx in enumerate(browser.contexts):
                    for page_idx, page in enumerate(ctx.pages):
                        title = await page.title()
                        url = page.url
                        screenshot_file = f"chrome_review_port_{port}_p{page_idx}.png"
                        screenshot_path = os.path.join(artifact_dir, screenshot_file)
                        await page.screenshot(path=screenshot_path)
                        
                        # Evaluate basic layout diagnostics
                        eval_info = {}
                        try:
                            eval_info = await page.evaluate("""() => {
                                return {
                                    title: document.title,
                                    url: window.location.href,
                                    gridCount: document.querySelectorAll('.grid-item, .layout-item, [class*="chart"]').length,
                                    tableCount: document.querySelectorAll('table, .cg-table, .tv-table').length,
                                    bodyTextSnippet: document.body.innerText.substring(0, 300)
                                };
                            }""")
                        except Exception as ee:
                            eval_info["error"] = str(ee)
                            
                        results[f"port_{port}"].append({
                            "context": ctx_idx,
                            "page_index": page_idx,
                            "title": title,
                            "url": url,
                            "screenshot": screenshot_path,
                            "eval": eval_info
                        })
                await browser.close()
            except Exception as e:
                # Port not open or no connection
                pass
                
    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    asyncio.run(review_chrome_instances())
