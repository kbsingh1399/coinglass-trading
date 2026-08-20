@echo off
title Engine 1 - Autonomous Live Trading System
cd /d "C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR"

:: Unbuffer Python output for immediate log flushing
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8

:: Pre-startup sweep: Terminate all Chrome instances on any port and stale Python workers
echo [CLEANUP] Terminating all Chrome instances and drivers across all ports...
taskkill /F /IM chrome.exe /T >nul 2>&1
taskkill /F /IM chromedriver.exe /T >nul 2>&1
taskkill /F /IM msedge.exe /T >nul 2>&1

echo [CLEANUP] Terminating stale Python engine workers...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"name = 'python.exe'\" | Where-Object { $_.CommandLine -notlike '*code_review_graph*' -and $_.CommandLine -notlike '*antigravity*' -and ($_.CommandLine -like '*Engine_1.py*' -or $_.CommandLine -like '*train_six_strategy*' -or $_.CommandLine -like '*desktop_auditor*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

:: Clean stale locks across all profiles
if exist "chrome_profile_tab1\SingletonLock" del /f /q "chrome_profile_tab1\SingletonLock" >nul 2>&1
if exist "chrome_profile_tab1\SingletonSocket" del /f /q "chrome_profile_tab1\SingletonSocket" >nul 2>&1
if exist "chrome_profile_tab1\SingletonCookie" del /f /q "chrome_profile_tab1\SingletonCookie" >nul 2>&1
if exist "chrome_profile_tab1\lockfile" del /f /q "chrome_profile_tab1\lockfile" >nul 2>&1
if exist "chrome_profile_tab2\SingletonLock" del /f /q "chrome_profile_tab2\SingletonLock" >nul 2>&1
if exist "chrome_profile_tab2\SingletonSocket" del /f /q "chrome_profile_tab2\SingletonSocket" >nul 2>&1
if exist "chrome_profile_tab2\SingletonCookie" del /f /q "chrome_profile_tab2\SingletonCookie" >nul 2>&1
if exist "chrome_profile_tab2\lockfile" del /f /q "chrome_profile_tab2\lockfile" >nul 2>&1

:: Pre-launch both Chrome GUI windows directly on interactive desktop screen
echo [LAUNCHER] Opening visible Google Chrome windows in foreground...
powershell -NoProfile -Command "Start-Process -FilePath 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList '--remote-debugging-port=9222', '--remote-allow-origins=*', '--start-maximized', '--user-data-dir=\"%~dp0chrome_profile_tab1\"', 'https://www.coinglass.com/login'"
powershell -NoProfile -Command "Start-Process -FilePath 'C:\Program Files\Google\Chrome\Application\chrome.exe' -ArgumentList '--remote-debugging-port=19900', '--remote-allow-origins=*', '--start-maximized', '--user-data-dir=\"%~dp0chrome_profile_tab2\"', 'https://www.coinglass.com/login'"
ping 127.0.0.1 -n 3 >nul

set PYTHON_EXE=C:\Users\SIGMA\AppData\Local\Python\pythoncore-3.14-64\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

:LOOP
cls
echo =====================================================================
echo  Engine 1 Autonomous Live Execution (Auto-Restart Watchdog Active)
echo  Directory: %CD%
echo  Log File: live_engine_output.txt
echo  Timestamp: %DATE% %TIME%
echo =====================================================================

:: Run Engine_1 directly in interactive console (FileTee in Engine_1 handles live_engine_output.txt natively)
"%PYTHON_EXE%" -u Engine_1.py --skip-train --skip-seed

echo.
echo =====================================================================
echo  [WATCHDOG] Engine exited or was reloaded by AI background daemon.
echo  [WATCHDOG] Relaunching in 5 seconds...
echo =====================================================================
ping 127.0.0.1 -n 6 >nul
goto LOOP
