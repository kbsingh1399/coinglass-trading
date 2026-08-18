import asyncio
from playwright.async_api import async_playwright
import json

async def check_dom():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://localhost:9222")
            contexts = browser.contexts
            if not contexts:
                print("No contexts found on 9222")
                return
            page = contexts[0].pages[0]
            
            # Fetch the inner text and HTML of the Liquidation indicator
            result = await page.evaluate('''() => {
                let iframes = document.querySelectorAll('iframe');
                if (iframes.length === 0) return {error: "No iframes"};
                
                let frameDoc = iframes[0].contentDocument || iframes[0].contentWindow.document;
                let studyItems = Array.from(frameDoc.querySelectorAll('.item-l31H9iuA.study-l31H9iuA, .pane-legend-item, [class*="legendItem"]'));
                let liqItem = studyItems.find(item => item.innerText.includes("Liquidations") || item.innerText.includes("LIQ"));
                
                if (!liqItem) return {error: "Liquidation item not found in first iframe"};
                
                let valSubEls = liqItem.querySelectorAll('.pane-legend-value, [class*="legendValue"], [class*="value"], [class*="valueValue-"]');
                let leafValEls = Array.from(valSubEls).filter(parent => !Array.from(valSubEls).some(child => parent !== child && parent.contains(child)));
                
                return {
                    fullText: liqItem.innerText,
                    html: liqItem.innerHTML,
                    leafClasses: leafValEls.map(el => el.className),
                    leafTexts: leafValEls.map(el => el.innerText)
                };
            }''')
            print(json.dumps(result, indent=2))
        except Exception as e:
            print("Error connecting to 9222:", e)

asyncio.run(check_dom())
