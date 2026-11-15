@echo off
setlocal
cd /d "%~dp0backend"
".venv\Scripts\python.exe" manage.py backup
if /i not "%~1"=="quiet" pause
