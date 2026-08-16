import ctypes
import os
import sys
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

SW_MAXIMIZE = 3
SW_RESTORE = 9
SW_SHOW = 5
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040

def force_to_front(hwnd):
    try:
        # Get thread IDs
        fore_hwnd = user32.GetForegroundWindow()
        fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None)
        app_thread = kernel32.GetCurrentThreadId()
        
        # Attach input thread to bypass Windows foreground lock restriction
        if fore_thread != app_thread:
            user32.AttachThreadInput(app_thread, fore_thread, True)
            user32.AttachThreadInput(fore_thread, app_thread, True)
        
        # Show maximized and make TopMost
        user32.ShowWindow(hwnd, SW_MAXIMIZE)
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
        
        # Reset TopMost so it behaves normally as the active window
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        
        if fore_thread != app_thread:
            user32.AttachThreadInput(app_thread, fore_thread, False)
            user32.AttachThreadInput(fore_thread, app_thread, False)
        return True
    except Exception as e:
        print(f"Error forcing hwnd {hwnd}: {e}")
        return False

def find_and_force_chrome_and_cmd():
    target_hwnds = []
    
    def enum_handler(hwnd, extra):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value
                t_lower = title.lower()
                if any(k in t_lower for k in ("coinglass", "chrome", "engine 1", "command prompt", "terminal", "node.js")):
                    if "antigravity" not in t_lower:
                        target_hwnds.append((hwnd, title))
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)
    user32.EnumWindows(WNDENUMPROC(enum_handler), 0)
    
    print(f"Found {len(target_hwnds)} candidate windows to force to front.")
    for hwnd, title in target_hwnds:
        print(f"-> Forcing to top of desktop: {title}")
        force_to_front(hwnd)
        time.sleep(0.1)

if __name__ == "__main__":
    find_and_force_chrome_and_cmd()
