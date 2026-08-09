from PIL import ImageGrab
import os
import ctypes
import time

out_path = r"C:\Users\SIGMA\.gemini\antigravity\brain\11e71ddd-8b3c-47ec-8aa3-8505db9c824f\desktop_terminal_screenshot.png"
log_path = r"C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR\autonomous_loop\capture_error.log"

os.makedirs(os.path.dirname(out_path), exist_ok=True)

EnumWindows = ctypes.windll.user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.POINTER(ctypes.c_int))
GetWindowText = ctypes.windll.user32.GetWindowTextW
GetWindowTextLength = ctypes.windll.user32.GetWindowTextLengthW
IsWindowVisible = ctypes.windll.user32.IsWindowVisible
ShowWindow = ctypes.windll.user32.ShowWindow
SetForegroundWindow = ctypes.windll.user32.SetForegroundWindow

with open(log_path, "w", encoding="utf-8") as lf:
    lf.write("Starting capture...\n")
    
    windows = []
    def foreach_window(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            GetWindowText(hwnd, buff, length + 1)
            title = buff.value
            if title:
                windows.append((hwnd, title))
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)
    
    # Locate the target console window specifically
    target_hwnd = None
    for hwnd, title in windows:
        if "Engine_1 Live Run" in title or "Engine_1_Live_Console" in title:
            target_hwnd = hwnd
            lf.write(f"Matched target console window: {title} (HWND: {hwnd})\n")
            break
            
    if target_hwnd:
        # Restore, Maximize, and bring to foreground
        ShowWindow(target_hwnd, 9)  # SW_RESTORE
        ShowWindow(target_hwnd, 3)  # SW_MAXIMIZE
        SetForegroundWindow(target_hwnd)
        time.sleep(2.0)
    else:
        lf.write("No matching terminal window found.\n")

    try:
        img = ImageGrab.grab()
        img.save(out_path)
        lf.write("Screenshot successfully saved.\n")
    except Exception as e:
        lf.write(f"Screenshot grab error: {e}\n")
