import asyncio
import os
import json
import time
from playwright.async_api import async_playwright

async def inspect_and_setup_tabs():
    artifact_dir = r"C:\Users\SIGMA\.gemini\antigravity-ide\brain\7a957850-be99-401e-96ea-ba3a22b4c818"
    os.makedirs(artifact_dir, exist_ok=True)
    
    async with async_playwright() as p:
        print("Connecting to Chrome on port 9222...")
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        
        pages = context.pages
        print(f"Initial open pages count: {len(pages)}")
        for idx, pg in enumerate(pages):
            print(f"  Page {idx+1}: {await pg.title()} ({pg.url})")
            
        # Ensure Page 1 is on https://www.coinglass.com/tv/layout/s9
        if len(pages) > 0:
            p1 = pages[0]
            if "layout/s9" not in p1.url:
                print("Navigating Page 1 to https://www.coinglass.com/tv/layout/s9 ...")
                await p1.goto("https://www.coinglass.com/tv/layout/s9")
                await asyncio.sleep(4.0)
        else:
            p1 = await context.new_page()
            await p1.goto("https://www.coinglass.com/tv/layout/s9")
            await asyncio.sleep(4.0)
            
        # Ensure Page 2 exists and is on https://www.coinglass.com/tv/layout/s9
        pages = context.pages
        if len(pages) < 2:
            print("Opening second s9 tab in the same Chrome instance...")
            p2 = await context.new_page()
            await p2.goto("https://www.coinglass.com/tv/layout/s9")
            print("Second s9 tab opened. Waiting for load...")
            await asyncio.sleep(5.0)
        else:
            p2 = pages[1]
            if "layout/s9" not in p2.url:
                print("Navigating Page 2 to https://www.coinglass.com/tv/layout/s9 ...")
                await p2.goto("https://www.coinglass.com/tv/layout/s9")
                await asyncio.sleep(4.0)

        # Refresh page list
        pages = context.pages
        print(f"\nFinal open pages count: {len(pages)}")
        
        all_tabs_data = []
        
        for tab_idx, page in enumerate(pages[:2]):
            tab_name = f"TAB_{tab_idx+1}"
            await page.bring_to_front()
            await asyncio.sleep(1.0)
            
            title = await page.title()
            url = page.url
            screenshot_file = f"coinglass_s9_tab_{tab_idx+1}.png"
            screenshot_path = os.path.join(artifact_dir, screenshot_file)
            await page.screenshot(path=screenshot_path)
            
            # Extract Main Page DOM
            main_dom = await page.evaluate("""() => {
                const data = {};
                data.title = document.title;
                data.url = window.location.href;
                
                // Top header texts & layout names
                const headers = Array.from(document.querySelectorAll('.header, [class*="header"], [class*="navbar"], [class*="tool"]')).map(el => el.innerText.trim()).filter(Boolean);
                data.headers_sample = headers.slice(0, 10);
                
                // Chart layout containers
                const containers = Array.from(document.querySelectorAll('[id*="tv_chart_container"], [class*="chart-container"], .grid-item, .layout-item')).map(c => ({
                    id: c.id,
                    className: c.className,
                    width: c.clientWidth,
                    height: c.clientHeight
                }));
                data.containers = containers;
                
                // Iframes
                const iframes = Array.from(document.querySelectorAll('iframe')).map((f, i) => ({
                    index: i,
                    id: f.id,
                    name: f.name,
                    src: f.src
                }));
                data.iframes = iframes;
                
                return data;
            }""")
            
            # Extract Data from each frame
            frames_summary = []
            for f_idx, frame in enumerate(page.frames):
                try:
                    frame_eval = await frame.evaluate("""() => {
                        const res = {};
                        res.url = window.location.href;
                        
                        // Extract symbol title
                        const symTitle = Array.from(document.querySelectorAll('[data-name="legend-series-item"], [class*="legend-series-title"], [class*="symbol-title"]')).map(el => el.innerText.trim()).filter(Boolean);
                        res.symbol_titles = symTitle;
                        
                        // Extract OHLC & Legend Values
                        const legendValues = Array.from(document.querySelectorAll('[class*="valuesWrapper"], [class*="valueValue"], [class*="itemValue"]')).map(el => el.innerText.trim()).filter(Boolean);
                        res.legend_values = legendValues;
                        
                        // Extract all text lines in the chart pane
                        const rawText = document.body ? document.body.innerText.split('\\n').map(l => l.trim()).filter(l => l.length > 0) : [];
                        res.text_lines = rawText;
                        
                        return res;
                    }""")
                    
                    if frame_eval.get("text_lines") or frame_eval.get("symbol_titles"):
                        frames_summary.append({
                            "frame_index": f_idx,
                            "name": frame.name,
                            "data": frame_eval
                        })
                except Exception as frame_err:
                    pass
                    
            tab_report = {
                "tab": tab_name,
                "title": title,
                "url": url,
                "screenshot": screenshot_path,
                "main_dom": main_dom,
                "active_frames": frames_summary
            }
            all_tabs_data.append(tab_report)
            
        json_report_path = os.path.join(artifact_dir, "live_chrome_s9_tabs_report.json")
        with open(json_report_path, "w", encoding="utf-8") as f:
            json.dump(all_tabs_data, f, indent=2)
            
        print(f"\n=======================================================")
        print(f"  LIVE DOM EXTRACTION COMPLETE - 2 S9 TABS ACTIVE")
        print(f"  Report saved: {json_report_path}")
        print(f"=======================================================")
        
        for t in all_tabs_data:
            print(f"\n--- {t['tab']} ({t['title']}) ---")
            print(f"URL: {t['url']}")
            print(f"Grid Containers: {len(t['main_dom']['containers'])}")
            print(f"Iframes: {len(t['main_dom']['iframes'])}")
            print(f"Active Chart Frames with Data: {len(t['active_frames'])}")
            for af in t['active_frames'][:9]:
                syms = af['data'].get('symbol_titles', [])
                sample_lines = af['data'].get('text_lines', [])[:6]
                print(f"  Frame #{af['frame_index']} ({af['name']}): Symbols={syms} | Text: {sample_lines}")

if __name__ == "__main__":
    asyncio.run(inspect_and_setup_tabs())
