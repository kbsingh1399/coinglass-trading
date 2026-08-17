import asyncio
import json
from playwright.async_api import async_playwright

async def inspect_tv_functions():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = browser.contexts[0].pages[0]
        frame = page.frames[1]
        
        info = await frame.evaluate("""() => {
            function getAllMethods(obj) {
                let props = new Set();
                let current = obj;
                while (current && current !== Object.prototype) {
                    Object.getOwnPropertyNames(current).forEach(p => {
                        if (typeof obj[p] === 'function') props.add(p);
                    });
                    current = Object.getPrototypeOf(current);
                }
                return Array.from(props);
            }
            
            let api = window.tradingViewApi;
            let chart = api.activeChart ? api.activeChart() : null;
            let widget = chart && chart._chartWidget ? chart._chartWidget : null;
            let collection = api._chartWidgetCollection ? api._chartWidgetCollection : null;
            
            return {
                apiMethods: getAllMethods(api),
                chartMethods: chart ? getAllMethods(chart) : [],
                widgetMethods: widget ? getAllMethods(widget) : [],
                collectionMethods: collection ? getAllMethods(collection) : [],
                activeSymbol: chart && chart.symbol ? chart.symbol() : null,
                activeResolution: chart && chart.resolution ? chart.resolution() : null
            };
        }""")
        print(json.dumps(info, indent=2))
        await browser.close()

if __name__ == "__main__":
    asyncio.run(inspect_tv_functions())
