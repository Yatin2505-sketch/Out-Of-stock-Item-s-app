@echo off
setlocal
cd /d "%~dp0backend"
title Stockbook - Reset a password
echo Use this if you forgot the admin password (or to add another admin).
echo.
".venv\Scripts\python.exe" manage.py create-admin
pause
