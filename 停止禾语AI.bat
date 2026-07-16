@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-windows.ps1"
if errorlevel 1 (
  echo.
  echo Failed to stop Heyu AI. Please keep this window open and report the message above.
  pause
  exit /b 1
)
echo.
echo Heyu AI has stopped.
pause
