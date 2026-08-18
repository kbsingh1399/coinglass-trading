@echo off
title Chrome Remote Debugging Launcher (Port 9222)
echo =====================================================================
echo  Launching Local Google Chrome in Debug Mode (Port 9222)
echo  Executable: C:\Program Files\Google\Chrome\Application\chrome.exe
echo =====================================================================

:: Clean stale profile locks if any
if exist "chrome_profile_tab1\SingletonLock" del /f /q "chrome_profile_tab1\SingletonLock"
if exist "chrome_profile_tab1\SingletonSocket" del /f /q "chrome_profile_tab1\SingletonSocket"
if exist "chrome_profile_tab1\SingletonCookie" del /f /q "chrome_profile_tab1\SingletonCookie"
if exist "chrome_profile_tab1\lockfile" del /f /q "chrome_profile_tab1\lockfile"

:: Start Google Chrome directly on your PC in maximized debug mode
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" ^
    --remote-debugging-port=9222 ^
    --start-maximized ^
    --window-position=0,0 ^
    --window-size=1920,1080 ^
    --no-first-run ^
    --no-default-browser-check ^
    --disable-background-timer-throttling ^
    --disable-backgrounding-occluded-windows ^
    --disable-renderer-backgrounding ^
    --user-data-dir="%~dp0chrome_profile_tab1" ^
    "https://www.coinglass.com/tv/layout/s9"

echo Chrome launched on port 9222.
exit /b 0
