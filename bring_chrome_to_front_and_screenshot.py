import os
import sys
import ctypes
import asyncio
from playwright.async_api import async_playwright

def bring_chrome_windows_to_front_and_maximize():
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    
    # ShowWindow commands: SW_RESTORE = 9, SW_MAXIMIZE = 3, SW_SHOWMAXIMIZED = 3
    found_windows = []
    
    def enum_handler(hwnd, extra):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                if "coinglass" in title.lower() or "chrome" in title.lower() or "binance" in title.lower():
                    found_windows.append((hwnd, title))
                    user32.ShowWindow(hwnd, 3) # SW_MAXIMIZE
                    user32.SetForegroundWindow(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(enum_handler), 0)
    print(f"[Windows] Found and maximized {len(found_windows)} windows: {found_windows}")

async def capture_cdp_screenshots():
    artifact_dir = r"C:\Users\SIGMA\.gemini\antigravity\brain\b0378007-cf33-45a3-a901-d12ca2793e08"
    
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    async with async_playwright() as p:
        for port, name in [(9222, "TAB_1"), (9223, "TAB_2")]:
            try:
                browser = await p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
                for context in browser.contexts:
                    for i, page in enumerate(context.pages):
                        out_path = os.path.join(artifact_dir, f"live_{name}_page_{i}.png")
                        await page.screenshot(path=out_path)
                        print(f"[CDP] Successfully captured live screenshot for {name} to {out_path}")
                await browser.close()
            except Exception as e:
                print(f"[CDP] Could not connect to port {port}: {e}")

if __name__ == "__main__":
    bring_chrome_windows_to_front_and_maximize()
    try:
        asyncio.run(capture_cdp_screenshots())
    except Exception as e:
        print(f"Error during CDP capture: {e}")
