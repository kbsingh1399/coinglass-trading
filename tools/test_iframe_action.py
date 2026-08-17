import asyncio
import json
from playwright.async_api import async_playwright

async def test_iframe_actions():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = browser.contexts[0].pages[0]
        
        # Test on frame 1
        frame = page.frames[1]
        
        res = await frame.evaluate("""() => {
            let api = window.tradingViewApi;
            let chart = api.activeChart ? api.activeChart() : null;
            let widget = chart && chart._chartWidget ? chart._chartWidget : null;
            
            let initialSym = chart.symbol();
            let initialRes = chart.resolution();
            
            // Try setting resolution directly via widget / chart
            if (widget && typeof widget.setResolution === 'function') {
                widget.setResolution('15', () => {});
            } else if (chart && typeof chart.setResolution === 'function') {
                chart.setResolution('15', () => {});
            }
            
            return {
                initialSym,
                initialRes,
                currentSym: chart.symbol(),
                currentRes: chart.resolution()
            };
        }""")
        print("Iframe Action Test Result:")
        print(json.dumps(res, indent=2))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test_iframe_actions())
