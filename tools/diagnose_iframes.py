import asyncio
import json
from playwright.async_api import async_playwright

async def inspect_iframes():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            page = browser.contexts[0].pages[0]
            print(f"Connected to page: {await page.title()} ({page.url})")
            
            # Find all container elements and iframes
            containers = await page.evaluate("""() => {
                let info = [];
                for (let i = 1; i <= 9; i++) {
                    let id = 'tv_chart_container_win' + i;
                    let el = document.getElementById(id) || (i === 1 ? document.getElementById('tv_chart_container_main') : null);
                    if (el) {
                        let iframe = el.querySelector('iframe');
                        info.push({
                            slot: i,
                            containerId: el.id,
                            iframeName: iframe ? iframe.name : null,
                            iframeSrc: iframe ? iframe.src.substring(0, 80) : null
                        });
                    }
                }
                return info;
            }""")
            print("Containers in DOM:")
            print(json.dumps(containers, indent=2))
            
            # Inspect each frame directly
            frames = page.frames
            print(f"\nTotal page frames: {len(frames)}")
            for idx, frame in enumerate(frames):
                if frame == page.main_frame:
                    continue
                try:
                    frame_info = await frame.evaluate("""() => {
                        return {
                            url: window.location.href,
                            hasTvApi: typeof window.tradingViewApi !== 'undefined',
                            hasTvWidget: typeof window.tvWidget !== 'undefined',
                            activeSymbol: document.querySelector('[class*="symbolTitle"], [class*="legend-"], .pane-legend')?.innerText || 'N/A',
                            resolutionButtons: Array.from(document.querySelectorAll('[data-value], [data-resolution], button')).map(b => b.innerText).filter(t => t && t.length < 10).slice(0, 10),
                            bodyClass: document.body.className
                        };
                    }""")
                    print(f"Frame {idx} ({frame.name}):")
                    print(json.dumps(frame_info, indent=2))
                except Exception as e:
                    print(f"Frame {idx} ({frame.name}) error: {e}")
            
            await browser.close()
        except Exception as ex:
            print(f"Inspection error: {ex}")

if __name__ == "__main__":
    asyncio.run(inspect_iframes())
