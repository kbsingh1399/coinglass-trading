import asyncio
import os
import sys
from playwright.async_api import async_playwright

async def check_and_set_15m():
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            for ctx in browser.contexts:
                for page in ctx.pages:
                    url = page.url
                    if "coinglass" in url:
                        print(f"Inspecting CoinGlass page: {url}")
                        
                        # Check top bar text
                        res = await page.evaluate('''() => {
                            const allElements = Array.from(document.querySelectorAll('*'));
                            const textNodes = allElements
                                .filter(el => el.children.length === 0 && ['1m', '3m', '5m', '15m', '30m', '1H', '1h', '4H', '4h', '1D', '1d'].includes(el.textContent.trim()))
                                .map(el => ({ tag: el.tagName, text: el.textContent.trim(), class: el.className }));
                            return textNodes;
                        }''')
                        print(f"Timeframe text elements found: {res}")
                        
                        # Try to find and click 15m or open interval dropdown
                        click_res = await page.evaluate('''() => {
                            // 1. Try finding exact '15m' element
                            const all = Array.from(document.querySelectorAll('*'));
                            const btn15 = all.find(el => el.textContent.trim() === '15m' && el.offsetParent !== null);
                            if (btn15) {
                                btn15.click();
                                return { success: true, method: 'direct_click_15m' };
                            }
                            
                            // 2. Try interval dropdown icon or chevron next to intervals
                            const chevron = all.find(el => (el.className && typeof el.className === 'string' && el.className.includes('interval')) || el.getAttribute('data-name') === 'time-interval');
                            if (chevron) {
                                chevron.click();
                            }
                            return { success: false, method: 'dropdown_attempted' };
                        }''')
                        print(f"Click attempt result: {click_res}")
                        
                        # Also inspect iframe tradingViewApi.activeChart().resolution() or setResolution('15')
                        for win_idx in range(1, 10):
                            container = page.locator(f"#tv_chart_container_win{win_idx}, #tv_chart_container_main").first
                            if await container.count() > 0:
                                iframe = container.locator("iframe").first
                                if await iframe.count() > 0:
                                    ih = await iframe.element_handle()
                                    if ih:
                                        frame = await ih.content_frame()
                                        if frame:
                                            f_res = await frame.evaluate('''() => {
                                                if (typeof tradingViewApi !== 'undefined' && tradingViewApi.activeChart) {
                                                    let ac = tradingViewApi.activeChart();
                                                    let curRes = ac.resolution ? ac.resolution() : 'unknown';
                                                    let setResOk = false;
                                                    try {
                                                        if (typeof ac.setResolution === 'function') {
                                                            ac.setResolution('15', () => {});
                                                            setResOk = true;
                                                        }
                                                    } catch(e) { setResOk = e.message; }
                                                    return { current: curRes, setResolution: setResOk };
                                                }
                                                return { error: 'no_api' };
                                            }''')
                                            print(f"Window {win_idx} chart resolution: {f_res}")
                        
            await browser.close()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(check_and_set_15m())
