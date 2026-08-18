"""
Run Full Engine_1 Pipeline with Visual Audit & Chrome in Full Mode
"""
import os
import sys
import time
import socket
import asyncio
import logging
import subprocess
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("VisualAuditPipeline")

ARTIFACTS_DIR = Path(r"C:\Users\SIGMA\.gemini\antigravity-ide\brain\7a957850-be99-401e-96ea-ba3a22b4c818")
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_EXE):
    CHROME_EXE = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

def is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except Exception:
        return False

def ensure_chrome_running(port: int, profile_dir: str):
    if not is_port_open(port):
        log.info(f"Launching Chrome in full mode on port {port} with profile {profile_dir}...")
        p_dir = os.path.abspath(profile_dir)
        os.makedirs(p_dir, exist_ok=True)
        cmd = [
            CHROME_EXE,
            f"--remote-debugging-port={port}",
            f"--user-data-dir={p_dir}",
            "--start-maximized",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--no-first-run",
            "--no-default-browser-check"
        ]
        subprocess.Popen(cmd)
        time.sleep(3.0)
    else:
        log.info(f"Chrome already active on port {port}.")

async def capture_and_verify_tabs():
    log.info("Capturing high-resolution visual screenshots for Tab 1 and Tab 2...")
    async with async_playwright() as p:
        # Tab 1
        try:
            b1 = await p.chromium.connect_over_cdp("http://127.0.0.1:19899")
            p1 = b1.contexts[0].pages[0] if b1.contexts[0].pages else None
            if p1:
                t1_path = ARTIFACTS_DIR / "tab1_fullscreen_audit.png"
                await p1.screenshot(path=str(t1_path), full_page=False)
                log.info(f"Saved Tab 1 visual audit screenshot: {t1_path}")
        except Exception as e:
            log.warning(f"Tab 1 screenshot note: {e}")

        # Tab 2
        try:
            b2 = await p.chromium.connect_over_cdp("http://127.0.0.1:19900")
            p2 = b2.contexts[0].pages[0] if b2.contexts[0].pages else None
            if p2:
                t2_path = ARTIFACTS_DIR / "tab2_fullscreen_audit.png"
                await p2.screenshot(path=str(t2_path), full_page=False)
                log.info(f"Saved Tab 2 visual audit screenshot: {t2_path}")
        except Exception as e:
            log.warning(f"Tab 2 screenshot note: {e}")

def main():
    log.info("=== 1. Ensuring Chrome Instances in Full Mode ===")
    ensure_chrome_running(19899, "chrome_profile_tab1")
    ensure_chrome_running(19900, "chrome_profile_tab2")

    log.info("=== 2. Running Setup and Verification ===")
    import tools.execute_perfect_coinglass_setup as setup_tool
    asyncio.run(setup_tool.main())

    log.info("=== 3. Capturing Visual Inspection Screenshots ===")
    asyncio.run(capture_and_verify_tabs())

    log.info("=== Setup & Visual Audit Complete ===")

if __name__ == "__main__":
    main()
