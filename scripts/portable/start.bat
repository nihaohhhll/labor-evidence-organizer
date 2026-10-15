@echo off
rem Labor Evidence Organizer - portable launcher (Windows)
rem Starts the API (:8000) and the web UI (:3000), then opens the browser.
setlocal enableextensions
set ROOT=%~dp0
set BACKEND_PORT=8000
set FRONTEND_PORT=3000

echo [1/4] Stopping previous instances...
call "%ROOT%stop.bat" silent

echo [2/4] Preparing data folder...
if not exist "%ROOT%data" mkdir "%ROOT%data"

cd /d "%ROOT%backend"
if not exist "%ROOT%data\leo.db" (
  echo       First run: creating database schema...
  "%ROOT%python\python.exe" -c "from app.db import create_all; create_all()"
  if errorlevel 1 (
    echo       Database initialization FAILED. See messages above.
    pause
    exit /b 1
  )
)

echo [3/4] Starting API on 127.0.0.1:%BACKEND_PORT% ...
start "LEO API :%BACKEND_PORT%" /min "%ROOT%start-backend.bat"

echo [4/4] Starting web UI on 127.0.0.1:%FRONTEND_PORT% ...
start "LEO Web :%FRONTEND_PORT%" /min "%ROOT%start-frontend.bat"

echo Waiting for services...
timeout /t 5 /nobreak >nul
start "" "http://127.0.0.1:%FRONTEND_PORT%"
echo.
echo Started. Keep the two "LEO" windows open while using the app.
echo Run stop.bat to shut everything down.
timeout /t 3 >nul
