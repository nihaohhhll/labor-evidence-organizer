@echo off
rem Labor Evidence Organizer - web UI (:3000). Started by start.bat.
setlocal enableextensions
set ROOT=%~dp0
set PORT=3000
set HOSTNAME=127.0.0.1
cd /d "%ROOT%frontend\server"
"%ROOT%frontend\node\node.exe" server.js
echo.
echo Web process exited with code %errorlevel%.
pause
