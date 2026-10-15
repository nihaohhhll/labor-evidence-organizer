@echo off
rem Labor Evidence Organizer - API backend (:8000). Started by start.bat.
setlocal enableextensions
set ROOT=%~dp0
cd /d "%ROOT%backend"
"%ROOT%python\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
echo.
echo API process exited with code %errorlevel%.
pause
