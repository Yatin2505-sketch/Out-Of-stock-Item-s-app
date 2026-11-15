@echo off
setlocal
cd /d "%~dp0backend"
title Stockbook - KEEP THIS WINDOW OPEN
if not exist ".venv\Scripts\python.exe" (
  echo Stockbook is not set up yet. Right-click "1-Setup.bat" and choose "Run as administrator".
  pause
  exit /b 1
)
".venv\Scripts\python.exe" manage.py backup >nul 2>&1
".venv\Scripts\python.exe" manage.py run
echo.
echo Stockbook has stopped. Double-click "2-Start-Stockbook.bat" to start it again.
pause
