@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Stockbook - Setup
echo.
echo  ==========================================================
echo     STOCKBOOK SETUP  (run this once)
echo  ==========================================================
echo.

rem ---- Needs administrator rights (firewall + auto-start) ----
net session >nul 2>&1
if errorlevel 1 (
  echo  Please close this window, RIGHT-CLICK "1-Setup.bat"
  echo  and choose "Run as administrator".
  echo.
  pause
  exit /b 1
)

rem ---- Step 1: find Python ----
echo  [1/6] Looking for Python...
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY python --version >nul 2>&1 && set "PY=python"
if not defined PY (
  echo        Python is not installed. Trying to install it automatically...
  winget install -e --id Python.Python.3.12 --scope machine --accept-package-agreements --accept-source-agreements
  echo.
  echo  ----------------------------------------------------------
  echo   If Python installed successfully, CLOSE this window and
  echo   run "1-Setup.bat" as administrator again.
  echo.
  echo   If it did not install, download Python from python.org,
  echo   and on the first install screen TICK "Add python.exe to PATH".
  echo  ----------------------------------------------------------
  pause
  exit /b 1
)
for /f "delims=" %%v in ('%PY% --version') do echo        Found %%v

rem ---- Step 2: private Python environment for the app ----
echo  [2/6] Preparing the app (first time takes a few minutes)...
if not exist "backend\.venv\Scripts\python.exe" (
  %PY% -m venv "backend\.venv"
  if errorlevel 1 goto :failed
)
set "APPPY=%~dp0backend\.venv\Scripts\python.exe"
"%APPPY%" -m pip install --quiet --upgrade pip
"%APPPY%" -m pip install --quiet -r "backend\requirements.txt"
if errorlevel 1 goto :failed
echo        Done.

rem ---- Step 3: settings file ----
if not exist "backend\.env" (
  > "backend\.env" echo # Stockbook settings. Lines starting with # are ignored.
  >>"backend\.env" echo # To save backups to a USB drive or second disk, remove the # below and set the folder:
  >>"backend\.env" echo # BACKUP_DIR=E:\StockbookBackups
  >>"backend\.env" echo # How many backups to keep:
  >>"backend\.env" echo KEEP_BACKUPS=60
  >>"backend\.env" echo STOCKBOOK_PORT=8000
)

rem ---- Step 4: admin login ----
echo.
echo  [3/6] Create the ADMIN login (for you / your father).
"%APPPY%" "backend\manage.py" create-admin
if errorlevel 1 goto :failed

rem ---- Step 5: allow phones to connect ----
echo.
echo  [4/6] Allowing phones on your network to open the app...
netsh advfirewall firewall delete rule name="Stockbook" >nul 2>&1
netsh advfirewall firewall add rule name="Stockbook" dir=in action=allow protocol=TCP localport=8000 profile=any >nul
echo        Done.

rem ---- Step 6: auto-start and daily backup ----
echo  [5/6] Starting automatically when this computer is turned on...
schtasks /Create /F /TN "Stockbook\Start" /SC ONLOGON /TR "\"%~dp02-Start-Stockbook.bat\"" >nul
echo        Done.
echo        Daily backup at 9:00 PM (and a backup every time the app starts)...
schtasks /Create /F /TN "Stockbook\Daily backup" /SC DAILY /ST 21:00 /TR "\"%~dp0Backup-Now.bat\" quiet" >nul
echo        Done.

echo.
echo  [6/6] This computer is now the app's server, so it should not go to sleep.
choice /C YN /M "        Turn off sleep while plugged in"
if errorlevel 2 (
  echo        Skipped. Remember: if the computer sleeps, the app stops working.
) else (
  powercfg /change standby-timeout-ac 0
  powercfg /change hibernate-timeout-ac 0
  echo        Sleep turned off.
)

echo.
echo  ==========================================================
echo    SETUP COMPLETE!
echo    Now double-click "2-Start-Stockbook.bat" to start the app.
echo  ==========================================================
pause
exit /b 0

:failed
echo.
echo  Something went wrong (see the messages above).
echo  Check the internet connection and run "1-Setup.bat" again.
pause
exit /b 1
