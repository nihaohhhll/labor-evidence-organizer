@echo off
rem Labor Evidence Organizer - API backend (:8000). Started by start.bat.
setlocal enableextensions
set ROOT=%~dp0
cd /d "%ROOT%backend"
rem --app-dir puts backend/ on sys.path explicitly: the embeddable python's
rem python311._pth forces safe_path (cwd is never added), so app.main must
rem not be resolved against the working directory.
"%ROOT%python\python.exe" -m uvicorn app.main:app --app-dir "%ROOT%backend" --host 127.0.0.1 --port 8000 --log-level info
echo.
echo API process exited with code %errorlevel%.
pause
