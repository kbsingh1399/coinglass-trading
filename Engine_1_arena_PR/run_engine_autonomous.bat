@echo off
title Engine 1 - Autonomous Live Trading System
cd /d "C:\Users\SIGMA\Documents\Project - Coinglass Trading\Engine_1_arena_PR"

:: Unbuffer Python output for immediate log flushing
set PYTHONUNBUFFERED=1
set PYTHONIOENCODING=utf-8

set PYTHON_EXE=C:\Users\SIGMA\AppData\Local\Python\pythoncore-3.14-64\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

:LOOP
cls
echo =====================================================================
echo  Engine 1 Autonomous Live Execution (Visible Desktop Console)
echo  Directory: %CD%
echo  Log File: live_engine_output.txt
echo  Timestamp: %DATE% %TIME%
echo =====================================================================

:: Run Engine_1 directly in visible interactive console
"%PYTHON_EXE%" -u Engine_1.py

echo.
echo =====================================================================
echo  [WATCHDOG] Engine exited or was reloaded by AI background daemon.
echo  [WATCHDOG] Relaunching in 5 seconds...
echo =====================================================================
timeout /t 5 /nobreak >nul
goto LOOP
