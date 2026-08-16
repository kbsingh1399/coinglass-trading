import os
import sys
import subprocess
import time
import urllib.request

def launch_debug_chrome():
    chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    user_data_dir = os.path.join(os.getcwd(), "chrome_profile_tab1")
    os.makedirs(user_data_dir, exist_ok=True)
    
    # Pre-clean lock files
    for lock in ("SingletonLock", "SingletonSocket", "SingletonCookie", "lockfile"):
        lp = os.path.join(user_data_dir, lock)
        if os.path.exists(lp):
            try: os.remove(lp)
            except Exception: pass

    cmd = [
        chrome_exe,
        "--remote-debugging-port=9222",
        "--start-maximized",
        "--window-position=0,0",
        "--window-size=1920,1080",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        f"--user-data-dir={user_data_dir}",
        "https://www.coinglass.com/tv/layout/s9"
    ]
    
    print("[Launcher] Spawning Google Chrome in Full-Screen Maximized Debug Mode on port 9222...")
    proc = subprocess.Popen(cmd)
    
    # Wait for CDP endpoint to become active
    for _ in range(20):
        try:
            with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1) as resp:
                if resp.status == 200:
                    print("[Launcher] Chrome Debug CDP active on http://127.0.0.1:9222")
                    break
        except Exception:
            time.sleep(0.5)

    # Use Playwright CDP to dismiss welcome page and load layout
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            ctx = b.contexts[0] if b.contexts else b
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://www.coinglass.com/tv/layout/s9", wait_until="domcontentloaded")
            print("[Launcher] Navigated to https://www.coinglass.com/tv/layout/s9 successfully!")
            b.close()
        except Exception as e:
            print(f"[Launcher] CDP navigation notice: {e}")
            
    return True

if __name__ == "__main__":
    launch_debug_chrome()
