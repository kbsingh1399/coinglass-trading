import time
import os
import subprocess
import sys
from datetime import datetime

def install_deps():
    try:
        import pygetwindow as gw
        from PIL import ImageGrab
    except ImportError:
        print("Installing required packages (pygetwindow, Pillow)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pygetwindow", "Pillow"])

install_deps()
import pygetwindow as gw
from PIL import ImageGrab

def cleanup_old_screenshots(save_dir: str, max_keep: int = 6):
    try:
        if not os.path.exists(save_dir):
            return
        files = sorted(
            [os.path.join(save_dir, f) for f in os.listdir(save_dir) if f.endswith(".png") and not f.startswith("latest_")],
            key=os.path.getmtime
        )
        if len(files) > max_keep:
            for f in files[:-max_keep]:
                try:
                    os.remove(f)
                except Exception:
                    pass
    except Exception as e:
        print(f"Cleanup error: {e}")

def robust_screen_grab():
    try:
        import mss
        from PIL import Image
        with mss.mss() as sct:
            mon = sct.monitors[0]
            sct_img = sct.grab(mon)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    except Exception:
        pass
    try:
        from PIL import ImageGrab
        return ImageGrab.grab()
    except Exception:
        pass
    return None

def take_desktop_screenshots():
    save_dir = r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\live_data\desktop_screenshots"
    os.makedirs(save_dir, exist_ok=True)
    cleanup_old_screenshots(save_dir, max_keep=6)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    print(f"[{stamp}] Activating windows and capturing desktop...")
    
    # 1. Bring Terminal to front & maximize
    terms = [
        w for w in gw.getAllWindows() 
        if any(k in (w.title or "").lower() for k in ["engine 1", "autonomous live", "footprint scraper", "node.js", "command prompt", "terminal", "powershell", "cmd"]) 
        and w.visible 
        and "antigravity" not in (w.title or "").lower() 
        and "visual studio" not in (w.title or "").lower()
    ]
    if terms:
        try:
            terms[0].restore()
        except: pass
        try:
            terms[0].maximize()
        except: pass
        try:
            terms[0].activate()
            time.sleep(1.5)
        except Exception as e:
            print(f"Failed to activate terminal: {e}")
            
    # Always take screen capture of current active view
    try:
        img = robust_screen_grab()
        if img:
            img.save(os.path.join(save_dir, f"{stamp}_0_terminal.png"))
            img.save(os.path.join(save_dir, "latest_terminal.png"))
            print(f"Captured terminal screenshot: {stamp}_0_terminal.png")
    except Exception as e:
        print(f"Failed to grab desktop: {e}")

    # 2. Bring Chrome windows to front & maximize
    chromes = [
        w for w in gw.getAllWindows() 
        if ("Google Chrome" in w.title or "coinglass" in w.title.lower() or "Arbitrum" in w.title or "Bitcoin" in w.title or "coinglass.com" in w.title.lower())
        and "Antigravity" not in w.title
        and "Visual Studio" not in w.title
        and "Cursor" not in w.title
        and w.visible and w.width > 200
    ]
    for i, chrome in enumerate(chromes):
        try:
            chrome.restore()
        except: pass
        try:
            chrome.maximize()
        except: pass
        try:
            chrome.activate()
            time.sleep(1.5)
            img = robust_screen_grab()
            if img:
                img.save(os.path.join(save_dir, f"{stamp}_{i+1}_chrome.png"))
                img.save(os.path.join(save_dir, f"latest_chrome_tab{i+1}.png"))
                print(f"Captured chrome window {i+1} ({chrome.title[:30]}...): {stamp}_{i+1}_chrome.png")
        except Exception as e:
            print(f"Failed to activate chrome: {e}")
            
    # Finally, bring Terminal back to the front
    if terms:
        try:
            terms[0].activate()
        except: pass

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        take_desktop_screenshots()
        sys.exit(0)
    print("Desktop Auditor running... taking full desktop snapshots every 5 minutes.")
    # Wait for Engine_1 to finish layout navigation and indicator injection
    time.sleep(45) 
    while True:
        take_desktop_screenshots()
        time.sleep(300)
