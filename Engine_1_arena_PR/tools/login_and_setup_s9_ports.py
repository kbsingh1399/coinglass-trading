import re
import asyncio
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("CoinGlassAuthSetup")

EMAIL_VAL = "singhkaranbir0248@gmail.com"
PASS_VAL = "Lu$er2hero"

async def auto_login_and_setup(port: int, tab_name: str) -> bool:
    endpoint_url = f"http://127.0.0.1:{port}"
    log.info(f"[{tab_name}] Connecting to Chrome on port {port}...")
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(endpoint_url)
        except Exception as e:
            log.error(f"[{tab_name}] Could not connect over CDP to port {port}: {e}")
            return False

        contexts = browser.contexts
        if not contexts:
            log.error(f"[{tab_name}] No browser contexts on port {port}.")
            return False

        context = contexts[0]
        pages = context.pages
        page = pages[0] if pages else await context.new_page()

        # Step 1: Login
        log.info(f"[{tab_name}] Navigating to Login page...")
        await page.goto("https://www.coinglass.com/login", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(2.0)

        # Check if already logged in or needs login
        try:
            email_field = page.get_by_role("textbox", name="Email")
            if await email_field.is_visible(timeout=4000):
                log.info(f"[{tab_name}] Entering credentials...")
                await email_field.click()
                await email_field.fill(EMAIL_VAL)
                
                pass_field = page.get_by_role("textbox", name="Password")
                await pass_field.click()
                await pass_field.fill(PASS_VAL)
                
                log.info(f"[{tab_name}] Submitting login...")
                login_btn = page.get_by_role("button", name="Login").nth(1)
                await login_btn.click()
                await asyncio.sleep(5.0)
            else:
                log.info(f"[{tab_name}] Email field not visible — already authenticated or session active.")
        except Exception as e:
            log.info(f"[{tab_name}] Login form interaction notice: {e}")

        # Step 2: Navigate to S9 layout
        log.info(f"[{tab_name}] Navigating to S9 Layout: https://www.coinglass.com/tv/layout/s9 ...")
        await page.goto("https://www.coinglass.com/tv/layout/s9", wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(6.0)

        # Step 3: Load L_1 Layout
        log.info(f"[{tab_name}] Attempting to load L_1 chart layout...")
        try:
            layout_btn = page.get_by_role("button").filter(has_text=re.compile(r"^$")).nth(3)
            if await layout_btn.is_visible(timeout=5000):
                log.info(f"[{tab_name}] Clicking layout menu button...")
                await layout_btn.click()
                await asyncio.sleep(1.0)
                
                load_item = page.get_by_role("menuitem", name="Load Chart Layout")
                if await load_item.is_visible(timeout=3000):
                    await load_item.click()
                    await asyncio.sleep(1.0)
                    
                    l1_btn = page.get_by_role("button", name="L_1")
                    if await l1_btn.is_visible(timeout=3000):
                        await l1_btn.click()
                        log.info(f"[{tab_name}] Successfully loaded L_1 layout!")
                        await asyncio.sleep(5.0)
                    else:
                        log.warning(f"[{tab_name}] 'L_1' layout button not found in menu.")
                else:
                    log.warning(f"[{tab_name}] 'Load Chart Layout' menu item not found.")
            else:
                log.warning(f"[{tab_name}] Layout dropdown button not visible.")
        except Exception as le:
            log.warning(f"[{tab_name}] L_1 load error / bypass: {le}")

        log.info(f"[{tab_name}] S9 tab ready on port {port}!")
        return True

async def main():
    ports = [
        (19899, "Tab_1"),
        (19900, "Tab_2")
    ]
    for port, name in ports:
        log.info(f"=== Running Authentication & S9 Setup for {name} ({port}) ===")
        await auto_login_and_setup(port, name)
        await asyncio.sleep(2.0)

if __name__ == "__main__":
    asyncio.run(main())
