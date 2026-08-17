import asyncio
import json
from playwright.async_api import async_playwright

async def inspect_tv_api():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = browser.contexts[0].pages[0]
        
        # Test on frame 1
        frame = page.frames[1] # tradingview_1eff5
        methods = await frame.evaluate("""() => {
            let res = {
                tvApiKeys: Object.keys(window.tradingViewApi || {}),
                chartKeys: [],
                symbolInfo: null
            };
            if (window.tradingViewApi && window.tradingViewApi.activeChart) {
                let chart = window.tradingViewApi.activeChart();
                res.chartKeys = Object.keys(chart);
                for (let key in chart) {
                    if (typeof chart[key] === 'function') {
                        res.chartKeys.push(key + '()');
                    }
                }
                if (typeof chart.symbol === 'function') {
                    res.symbol = chart.symbol();
                }
                if (typeof chart.resolution === 'function') {
                    res.resolution = chart.resolution();
                }
            }
            return res;
        }""")
        print("TradingView API Inspection:")
        print(json.dumps(methods, indent=2))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_tv_api())
