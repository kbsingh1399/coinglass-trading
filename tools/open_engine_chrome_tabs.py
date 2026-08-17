"""
Launch and verify Chrome instances on the exact ports used by Engine_1 (Port 19899 and Port 19900).
"""

import os
import sys
import time
import socket
import subprocess
from pathlib import Path

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
if not os.path.exists(CHROME_EXE):
    CHROME_EXE = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

def is_port_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except Exception:
        return False

def launch_chrome_port(port: int, profile_name: str):
    p_dir = os.path.abspath(profile_name)
    os.makedirs(p_dir, exist_ok=True)
    if is_port_open(port):
        print(f" [OK] Port {port} is already ACTIVE and listening (Profile: {profile_name}).")
        return

    print(f" [LAUNCH] Starting Chrome in full mode on Port {port} (Profile: {profile_name})...")
    cmd = [
        CHROME_EXE,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={p_dir}",
        "--start-maximized",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--no-first-run",
        "--no-default-browser-check",
        "https://www.coinglass.com/tv/layout/s9"
    ]
    subprocess.Popen(cmd)
    
    # Wait for socket to become available
    for _ in range(10):
        time.sleep(0.5)
        if is_port_open(port):
            print(f" [SUCCESS] Port {port} is now OPEN and ready for CDP connections.")
            return
            
    print(f" [WARN] Port {port} did not respond within 5 seconds.")

def main():
    print("=" * 70)
    print("  LAUNCHING ENGINE_1 DEDICATED CHROME TABS")
    print("=" * 70)
    
    # Tab 1: Port 19899
    launch_chrome_port(19899, "chrome_profile_tab1")
    
    # Tab 2: Port 19900
    launch_chrome_port(19900, "chrome_profile_tab2")
    
    print("=" * 70)
    print(f"  Tab 1 Status (Port 19899): {'ONLINE' if is_port_open(19899) else 'OFFLINE'}")
    print(f"  Tab 2 Status (Port 19900): {'ONLINE' if is_port_open(19900) else 'OFFLINE'}")
    print("=" * 70)

if __name__ == "__main__":
    main()
