import asyncio
import sys
import logging
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("ChromePortSetup")

LOGIN_URL = "https://www.coinglass.com/login"
S9_URL = "https://www.coinglass.com/tv/layout/s9"

async def configure_chrome_instance(port: int, instance_name: str) -> bool:
    endpoint_url = f"http://127.0.0.1:{port}"
    log.info(f"[{instance_name}] Connecting to Chrome on port {port} ({endpoint_url})...")
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(endpoint_url)
        except Exception as e:
            log.error(f"[{instance_name}] Failed to connect to Chrome on port {port}: {e}")
            return False

        contexts = browser.contexts
        if not contexts:
            log.error(f"[{instance_name}] No browser contexts found on port {port}.")
            return False

        context = contexts[0]
        pages = context.pages

        # Step 1: Open Login Page
        log.info(f"[{instance_name}] Step 1: Navigating to Login page ({LOGIN_URL})...")
        if pages:
            login_page = pages[0]
            await login_page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
        else:
            login_page = await context.new_page()
            await login_page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)

        log.info(f"[{instance_name}] Login page loaded successfully: {login_page.url}")
        await asyncio.sleep(2.0)

        # Step 2: Open S9 Layout in a new tab
        log.info(f"[{instance_name}] Step 2: Opening S9 layout page in new tab ({S9_URL})...")
        s9_page = await context.new_page()
        await s9_page.goto(S9_URL, wait_until="domcontentloaded", timeout=60000)
        log.info(f"[{instance_name}] S9 layout page opened successfully: {s9_page.url}")
        await asyncio.sleep(3.0)

        # Step 3: Close the login page/tab
        log.info(f"[{instance_name}] Step 3: Closing the login page tab...")
        try:
            await login_page.close()
            log.info(f"[{instance_name}] Login page closed. S9 tab is now active.")
        except Exception as e:
            log.warning(f"[{instance_name}] Error closing login page: {e}")

        # Bring S9 page to front
        await s9_page.bring_to_front()
        log.info(f"[{instance_name}] S9 setup sequence complete on port {port}!")
        return True

async def main():
    ports = [
        (19899, "Tab_1"),
        (19900, "Tab_2")
    ]
    
    results = {}
    for port, name in ports:
        log.info(f"--- Starting Configuration for {name} (Port {port}) ---")
        ok = await configure_chrome_instance(port, name)
        results[name] = ok
        await asyncio.sleep(2.0)
        
    log.info(f"Summary Results: {results}")

if __name__ == "__main__":
    asyncio.run(main())
