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
            print('Trying BingX_CLUSDT...')
            res = await f.evaluate('try { tradingViewApi.activeChart().setSymbol("BingX_CLUSDT"); return "OK"; } catch(e) { return String(e); }')
            print(f'Result 1: {res}')
            await page.wait_for_timeout(5000)
            
            err = await page.evaluate('document.body.innerText.includes("Minified Redux error #14")')
            print(f'Redux Error 14: {err}')
            
            print('Trying Binance_LTCUSDT...')
            res2 = await f.evaluate('try { tradingViewApi.activeChart().setSymbol("Binance_LTCUSDT"); return "OK"; } catch(e) { return String(e); }')
            print(f'Result 2: {res2}')
            await page.wait_for_timeout(5000)
            
            err2 = await page.evaluate('document.body.innerText.includes("Minified Redux error #14")')
            print(f'Redux Error 14: {err2}')
            
        await browser.close()

asyncio.run(run())
