import time
import os
import ctypes
from PIL import ImageGrab

def capture_terminal():
    user32 = ctypes.windll.user32
    
    # Enumerate windows and find "Engine 1" or "cmd.exe"
    EnumWindows = user32.EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    GetWindowText = user32.GetWindowTextW
    GetWindowTextLength = user32.GetWindowTextLengthW
    IsWindowVisible = user32.IsWindowVisible

    target_hwnd = None

    def foreach_window(hwnd, lParam):
        nonlocal target_hwnd
        if IsWindowVisible(hwnd):
            length = GetWindowTextLength(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                GetWindowText(hwnd, buff, length + 1)
                title = buff.value
                if "Engine 1" in title or "Autonomous Live Trading" in title or "cmd.exe" in title:
                    target_hwnd = hwnd
                    return False
        return True

    EnumWindows(EnumWindowsProc(foreach_window), 0)

    if target_hwnd:
        SW_RESTORE = 9
        user32.ShowWindow(target_hwnd, SW_RESTORE)
        user32.SetForegroundWindow(target_hwnd)
        time.sleep(1.0)

    # Capture primary screen
    img = ImageGrab.grab()
    artifact_dir = r"C:\Users\SIGMA\.gemini\antigravity\brain\b0378007-cf33-45a3-a901-d12ca2793e08"
    out_path = os.path.join(artifact_dir, "terminal_verification.png")
    img.save(out_path)
    print(f"[OK] Screen captured and saved to {out_path}")

if __name__ == "__main__":
    capture_terminal()
