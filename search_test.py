import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        await page.goto('https://www.coinglass.com/tv/layout/s9')
        await page.wait_for_timeout(10000)
        
        print('Clicking first search button...')
        try:
            search_btn = page.locator('button:has(svg[data-testid="SearchIcon"])').first
            await search_btn.click()
            await page.wait_for_timeout(2000)
            print('Clicked successfully!')
        except Exception as e:
            print('Click failed:', e)
        
        # Dump DOM
        content = await page.content()
        with open('C:\\Users\\SIGMA\\.gemini\\antigravity\\brain\\b0378007-cf33-45a3-a901-d12ca2793e08\\search_dialog_dom.html', 'w', encoding='utf-8') as f:
            f.write(content)
        print('Search Dialog DOM dumped!')
        
        # Take a screenshot
        await page.screenshot(path='C:\\Users\\SIGMA\\.gemini\\antigravity\\brain\\b0378007-cf33-45a3-a901-d12ca2793e08\\search_dialog_screenshot.png')
        print('Screenshot saved!')
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
