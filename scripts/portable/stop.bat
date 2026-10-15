@echo off
rem Labor Evidence Organizer - stop all services (Windows)
setlocal enableextensions
if "%1"=="silent" (
  rem called from start.bat - quiet mode
) else (
  echo Stopping Labor Evidence Organizer...
)

rem Kill whatever listens on the app ports. The trailing space in the
rem patterns avoids matching e.g. port 30001.
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r ":8000  *LISTENING"') do (
  taskkill /f /pid %%p >nul 2>&1
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /r ":3000  *LISTENING"') do (
  taskkill /f /pid %%p >nul 2>&1
)

if "%1"=="silent" exit /b 0
echo Done.
timeout /t 2 >nul
