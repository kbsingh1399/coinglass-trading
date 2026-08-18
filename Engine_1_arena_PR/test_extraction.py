import asyncio
from playwright.async_api import async_playwright

SINGLE_FRAME_EXTRACTION_JS = r'''() => {
    let getTxt = el => el ? (el.innerText || el.textContent || '').trim() : '';
    let legends = Array.from(document.querySelectorAll('.pane-legend-item, [class*="legendItem"], [class*="study"], [data-name="legend-source-item"]'));
    let res = [];
    for (let el of legends) {
        let text = getTxt(el);
        if (!text) continue;
        let upper = text.toUpperCase();
        if (upper.includes('LIQUIDATION') || upper.includes('LIQ')) {
            let badgeEls = Array.from(el.querySelectorAll('[class*="valueValue"], [class*="valueItem"], .apply-common-tooltip'));
            badgeEls = badgeEls.filter(b => !badgeEls.some(child => b.contains(child) && child !== b));
            let badgeTexts = badgeEls.map(b => getTxt(b)).filter(s => s && /[-+]?[0-9]/.test(s));
            
            let allTextNums = (badgeTexts.length > 0 ? badgeTexts : (text.match(/[-+]?[0-9,]+(?:\.[0-9]+)?[KMBkmb%]?/g) || [])).filter(s => s && s !== '-' && s !== '+');
            res.push({
                fullText: text,
                badgeTexts: badgeTexts,
                allTextNums: allTextNums
            });
        }
    }
    return res;
}'''

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print('Navigating to Coinglass...')
        await page.goto('https://www.coinglass.com/pro/futures/LiquidationHeatMap', timeout=60000)
        print('Waiting 10s for charts to load...')
        await asyncio.sleep(10)
        
        # We need to find iframes since Coinglass charts are in iframes
        frames = page.frames
        print(f'Found {len(frames)} frames')
        
        all_res = []
        for f in frames:
            try:
                res = await f.evaluate(SINGLE_FRAME_EXTRACTION_JS)
                if res:
                    all_res.extend(res)
            except Exception as e:
                pass
                
        print('Extraction Result:')
        for r in all_res:
            print(r)
            
        await browser.close()

if __name__ == '__main__':
    asyncio.run(run())
