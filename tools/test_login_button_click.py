import os
import re
import time
import asyncio
import subprocess
from playwright.async_api import async_playwright

async def inspect_login_page():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:19899")
        except Exception:
            print("Launching Chrome on port 19899...")
            p_dir = os.path.abspath("chrome_profile_tab1")
            os.makedirs(p_dir, exist_ok=True)
            cmd = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                "--remote-debugging-port=19899",
                f"--user-data-dir={p_dir}",
                "--start-maximized",
                "--no-first-run",
                "--no-default-browser-check"
            ]
            subprocess.Popen(cmd)
            time.sleep(3.0)
            browser = await p.chromium.connect_over_cdp("http://127.0.0.1:19899")
        context = browser.contexts[0]
        page = await context.new_page()
        print("Navigating to https://www.coinglass.com/login ...")
        await page.goto("https://www.coinglass.com/login", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(3.0)
        
        print("Finding textboxes...")
        textboxes = await page.get_by_role("textbox").all()
        for idx, tb in enumerate(textboxes):
            name = await tb.get_attribute("name")
            placeholder = await tb.get_attribute("placeholder")
            aria = await tb.get_attribute("aria-label")
            print(f"Textbox {idx}: name='{name}', placeholder='{placeholder}', aria='{aria}'")
            
        print("\nFinding all buttons...")
        buttons = await page.get_by_role("button").all()
        for idx, btn in enumerate(buttons):
            text = (await btn.inner_text() or "").strip()
            btn_type = await btn.get_attribute("type")
            cls = await btn.get_attribute("class")
            print(f"Button {idx}: text='{text}', type='{btn_type}', class='{cls[:50] if cls else ''}'")

        # Now fill email and password
        print("\nFilling email...")
        email_box = page.locator("input[type='email'], input[name='email'], input[placeholder*='Email'], input[type='text']").first
        if await email_box.is_visible():
            await email_box.click()
            await email_box.fill("singhkaranbir0248@gmail.com")
            print("Email filled.")
            
        print("Filling password...")
        pass_box = page.locator("input[type='password']").first
        if await pass_box.is_visible():
            await pass_box.click()
            await pass_box.fill("Lu$er2hero")
            print("Password filled.")
            
        print("\nAttempting to hit Login button...")
        # Try multiple candidate locators
        target_btn = None
        for cand in [
            page.get_by_role("button", name=re.compile(r"log\s*in", re.I)).nth(1),
            page.get_by_role("button", name=re.compile(r"log\s*in", re.I)).first,
            page.locator("button[type='submit']"),
            page.locator("form button"),
            page.locator("button").filter(has_text=re.compile(r"log\s*in|sign\s*in", re.I)).first,
        ]:
            try:
                if await cand.is_visible(timeout=1000):
                    target_btn = cand
                    txt = await cand.inner_text()
                    print(f"Found candidate button: '{txt}'")
                    break
            except Exception:
                pass
                
        if target_btn:
            print("Clicking target login button...")
            await target_btn.click()
            print("Target login button CLICKED!")
        else:
            print("Pressing Enter on password box...")
            await pass_box.press("Enter")
            print("Enter key pressed on password box!")
            
        print("Waiting 5 seconds for authentication tokens to settle...")
        await asyncio.sleep(5.0)
        
        cookies = await context.cookies()
        print(f"Captured {len(cookies)} cookies after login.")
        for c in cookies:
            if any(k in c['name'].lower() for k in ('token', 'user', 'session', 'cg', 'auth')):
                print(f"  Cookie: {c['name']} = {c['value'][:20]}...")
                
        await page.close()

if __name__ == "__main__":
    asyncio.run(inspect_login_page())
