import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        await page.goto('https://www.coinglass.com/tv/layout/s9')
        await page.wait_for_timeout(10000)
        
        frames = [f for f in page.frames if 'tradingview' in f.url or f != page.main_frame]
        if frames:
            f = frames[0]
            # Test OILWTIUSDT.P
            print('Trying BingX_OILWTIUSDT.P...')
            res = await f.evaluate('() => { try { tradingViewApi.activeChart().setSymbol("BingX_OILWTIUSDT.P"); return "OK"; } catch(e) { return String(e); } }')
            print('Result WTI:', res)
            await page.wait_for_timeout(5000)
            
            err = await page.evaluate('document.body.innerText.includes("Minified Redux error #14")')
            print('Redux Error WTI:', err)
            
            # Test NATURALGASNGUSDT.P
            print('Trying BingX_NATURALGASNGUSDT.P...')
            res2 = await f.evaluate('() => { try { tradingViewApi.activeChart().setSymbol("BingX_NATURALGASNGUSDT.P"); return "OK"; } catch(e) { return String(e); } }')
            print('Result NG:', res2)
            await page.wait_for_timeout(5000)
            
            err2 = await page.evaluate('document.body.innerText.includes("Minified Redux error #14")')
            print('Redux Error NG:', err2)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
