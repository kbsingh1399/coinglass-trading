@echo off
title Engine 1 - Autonomous Live Trading System
cd /d "C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR"

:: Unbuffer Python output for immediate log flushing
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8

:: Forcefully terminate any existing python or chrome instances
echo [CLEANUP] Forcefully terminating existing python and chrome instances...
taskkill /F /IM python.exe /T >nul 2>&1
taskkill /F /IM chrome.exe /T >nul 2>&1
timeout /t 2 /nobreak >nul

:: Launch Desktop Auditor in background to take physical desktop snapshots
start "Desktop Auditor" /B python desktop_auditor.py

:LOOP
cls
echo =====================================================================
echo  Engine 1 Autonomous Live Execution (Auto-Restart Watchdog Active)
echo  Directory: %CD%
echo  Log File: live_engine_output.txt
echo  Timestamp: %DATE% %TIME%
echo =====================================================================

:: Run Engine_1 directly in interactive console (FileTee in Engine_1 handles live_engine_output.txt natively)
python -u Engine_1.py --skip-train --skip-seed

echo.
echo =====================================================================
echo  [WATCHDOG] Engine exited or was reloaded by AI background daemon.
echo  [WATCHDOG] Relaunching in 5 seconds...
echo =====================================================================
timeout /t 5 /nobreak >nul
goto LOOP
